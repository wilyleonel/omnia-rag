"""
Omnia Memory — Memoria episódica con decaimiento temporal.

Cada recuerdo tiene un score que aumenta cuando se usa y decae con el tiempo.
Los recuerdos irrelevantes se desvanecen solos. El contexto siempre refleja
cómo trabajas HOY, no hace meses.

Fórmula de decaimiento:
    effective_score = (importance * use_count) * exp(-decay_rate * días_sin_usar)

- Si usas un recuerdo → score sube, reloj de decay se resetea.
- Si lo ignoras → score baja exponencialmente → se purga solo.
"""

import sqlite3
import math
import time
import uuid
import os
from datetime import datetime, timezone
from typing import Optional, List

# Días sin uso para que la score caiga al 10% de su valor original
DEFAULT_DECAY_HALF_LIFE_DAYS = 30
DECAY_RATE = math.log(10) / DEFAULT_DECAY_HALF_LIFE_DAYS  # ~0.077

# Score mínima antes de ser elegible para purga automática
PRUNE_THRESHOLD = 0.05

# Días de inactividad para que una sesión se elimine automáticamente
SESSION_DECAY_DAYS = 30

MEMORY_TYPES = {"rule", "pattern", "insight", "decision", "context"}

# Distancia coseno máxima para considerar dos recuerdos como duplicados semánticos
DEDUP_DISTANCE_THRESHOLD = 0.05


class MemoryStore:
    """
    Almacén de memoria episódica sobre SQLite.
    No necesita embedder propio: usa el de OmniaIndexer si está disponible,
    y cae back a búsqueda por texto si no.
    """

    def __init__(self, db_path: str, chroma_client=None, embedding_function=None, indexer=None):
        self.db_path = db_path
        self.indexer = indexer  # OmniaIndexer opcional para búsqueda semántica (legacy)
        self.chroma_client = chroma_client
        self.embedding_function = embedding_function
        self.collection = None
        if self.chroma_client and self.embedding_function:
            try:
                self.collection = self.chroma_client.get_or_create_collection(
                    name="omnia_episodic_memory",
                    embedding_function=self.embedding_function,
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception as e:
                import logging
                logging.error(f"Error initializing memory collection: {e}")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    # ─────────────────────────────── DB ────────────────────────────────── #

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.create_function("compute_decay", 3, self._compute_score)
        return conn

    def _init_db(self):
        with self._conn() as conn:
            # Tabla de sesiones nombradas
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    name        TEXT PRIMARY KEY,
                    description TEXT NOT NULL DEFAULT '',
                    created_at  REAL NOT NULL,
                    last_used   REAL NOT NULL
                )
            """)
            # Sesión global siempre existe
            now = time.time()
            conn.execute(
                "INSERT OR IGNORE INTO sessions (name, description, created_at, last_used) VALUES (?, ?, ?, ?)",
                ("global", "Memoria compartida entre todas las sesiones", now, now),
            )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id          TEXT PRIMARY KEY,
                    content     TEXT NOT NULL,
                    type        TEXT NOT NULL DEFAULT 'insight',
                    tags        TEXT NOT NULL DEFAULT '',
                    importance  REAL NOT NULL DEFAULT 1.0,
                    use_count   INTEGER NOT NULL DEFAULT 1,
                    created_at  REAL NOT NULL,
                    last_used   REAL NOT NULL,
                    score       REAL NOT NULL DEFAULT 1.0,
                    session     TEXT NOT NULL DEFAULT 'global'
                )
            """)
            # Migración: agregar columna session si ya existe la tabla sin ella
            try:
                conn.execute("ALTER TABLE memories ADD COLUMN session TEXT NOT NULL DEFAULT 'global'")
            except Exception:
                pass  # Ya existe

            conn.execute("CREATE INDEX IF NOT EXISTS idx_score   ON memories(score DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_type    ON memories(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON memories(session)")

    # ─────────────────────── Score & Decay ─────────────────────────────── #

    def _compute_score(self, importance: float, use_count: int, last_used: float) -> float:
        """Calcula el effective_score actual de un recuerdo."""
        days_since = (time.time() - last_used) / 86400.0
        return (importance * use_count) * math.exp(-DECAY_RATE * days_since)


    # ─────────────────────── Sesiones ──────────────────────────────────── #

    def session_create(self, name: str, description: str = "") -> dict:
        """Crea una sesión nueva. Si ya existe, la devuelve sin modificar."""
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (name, description, created_at, last_used) VALUES (?,?,?,?)",
                (name.strip(), description.strip(), now, now),
            )
            row = conn.execute("SELECT * FROM sessions WHERE name=?", (name,)).fetchone()
        return self._session_to_dict(row)

    def session_list(self) -> List[dict]:
        """Lista todas las sesiones con sus estadísticas."""
        with self._conn() as conn:
            sessions = conn.execute(
                "SELECT * FROM sessions ORDER BY last_used DESC"
            ).fetchall()
            result = []
            for s in sessions:
                mem_count = conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE session=?", (s["name"],)
                ).fetchone()[0]
                d = self._session_to_dict(s)
                d["memory_count"] = mem_count
                result.append(d)
        return result

    def session_touch(self, name: str) -> bool:
        """Marca una sesión como usada ahora (resetea su decay)."""
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE sessions SET last_used=? WHERE name=?", (time.time(), name)
            )
        return cursor.rowcount > 0

    def session_delete(self, name: str) -> dict:
        """Elimina una sesión y TODAS sus memorias."""
        if name == "global":
            raise ValueError("No puedes eliminar la sesión 'global'")
        with self._conn() as conn:
            mems = conn.execute("DELETE FROM memories WHERE session=?", (name,)).rowcount
            conn.execute("DELETE FROM sessions WHERE name=?", (name,))
        if mems > 0 and self.collection is not None:
            try:
                self.collection.delete(where={"session": name})
            except Exception:
                pass
        return {"session": name, "memories_deleted": mems}

    def session_prune_old(self, days: int = SESSION_DECAY_DAYS) -> List[dict]:
        """Elimina sesiones inactivas por más de `days` días junto con sus memorias."""
        cutoff = time.time() - (days * 86400)
        with self._conn() as conn:
            old = conn.execute(
                "SELECT name FROM sessions WHERE name != 'global' AND last_used < ?",
                (cutoff,),
            ).fetchall()
            pruned = []
            for row in old:
                sname = row["name"]
                mems = conn.execute("DELETE FROM memories WHERE session=?", (sname,)).rowcount
                conn.execute("DELETE FROM sessions WHERE name=?", (sname,))
                if mems > 0 and self.collection is not None:
                    try:
                        self.collection.delete(where={"session": sname})
                    except Exception:
                        pass
                pruned.append({"session": sname, "memories_deleted": mems})
        return pruned

    # ──────────────────────────── CRUD ─────────────────────────────────── #

    def _find_duplicate(self, content: str, type: str, session: str) -> Optional[str]:
        """Busca un recuerdo semánticamente casi-idéntico en la misma sesión/tipo,
        para evitar acumular duplicados con cada `add()`."""
        if self.collection is None:
            return None
        try:
            results = self.collection.query(
                query_texts=[content],
                n_results=1,
                where={"$and": [{"type": type}, {"session": session}]},
            )
            ids = results.get("ids", [[]])[0]
            distances = results.get("distances", [[]])[0]
            if ids and distances and distances[0] <= DEDUP_DISTANCE_THRESHOLD:
                return ids[0]
        except Exception:
            pass
        return None

    def add(
        self,
        content: str,
        type: str = "insight",
        tags: Optional[List[str]] = None,
        importance: float = 1.0,
        session: str = "global",
    ) -> dict:
        """Guarda un nuevo recuerdo en la sesión indicada. Si ya existe uno casi
        idéntico (mismo tipo/sesión), refuerza ese en vez de duplicarlo."""
        if type not in MEMORY_TYPES:
            raise ValueError(f"Tipo inválido. Usa: {MEMORY_TYPES}")

        content = content.strip()
        duplicate_id = self._find_duplicate(content, type, session)
        if duplicate_id:
            return self.boost(duplicate_id, extra_importance=0.1) or self.get(duplicate_id)

        now = time.time()
        memory_id = uuid.uuid4().hex
        tags_str = ",".join(tags or [])

        with self._conn() as conn:
            # Asegurar que la sesión existe; si no, crearla
            conn.execute(
                "INSERT OR IGNORE INTO sessions (name, description, created_at, last_used) VALUES (?,?,?,?)",
                (session, "", now, now),
            )
            # Actualizar last_used de la sesión
            conn.execute("UPDATE sessions SET last_used=? WHERE name=?", (now, session))

            conn.execute(
                """INSERT INTO memories (id, content, type, tags, importance, use_count, created_at, last_used, score, session)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
                (memory_id, content, type, tags_str, importance, now, now, importance, session),
            )

        if self.collection is not None:
            try:
                self.collection.add(
                    documents=[content],
                    metadatas=[{"type": type, "session": session}],
                    ids=[memory_id]
                )
            except Exception as e:
                import logging
                logging.error(f"Error indexing memory to ChromaDB: {e}")
                # Revertir el insert en SQLite para no dejar un recuerdo invisible
                # para recall() (que depende del índice vectorial salvo fallback).
                with self._conn() as conn:
                    conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
                raise RuntimeError(f"No se pudo indexar el recuerdo en ChromaDB, operación revertida: {e}") from e

        return self.get(memory_id)

    def get(self, memory_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            return self._row_to_dict(row) if row else None

    def list_all(self, limit: int = 50, type_filter: Optional[str] = None, session: Optional[str] = None) -> List[dict]:
        with self._conn() as conn:
            conditions = []
            params: list = []
            if type_filter:
                conditions.append("type=?")
                params.append(type_filter)
            if session:
                conditions.append("session=?")
                params.append(session)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            rows = conn.execute(f"SELECT * FROM memories {where}", params).fetchall()
            
        scored_rows = []
        for r in rows:
            d = dict(r)
            d["score"] = self._compute_score(d["importance"], d["use_count"], d["last_used"])
            scored_rows.append(d)
            
        scored_rows.sort(key=lambda x: x["score"], reverse=True)
        return [self._row_to_dict(r) for r in scored_rows[:limit]]

    def recall(self, query: str, top_k: int = 5, type_filter: Optional[str] = None, session: Optional[str] = None) -> List[dict]:
        """
        Busca recuerdos relevantes para `query`.
        session=None  → busca en TODAS las sesiones (contexto unificado)
        session="crm" → busca solo en esa sesión
        """
        top_rows = []
        
        if self.collection is not None:
            try:
                where = {}
                if type_filter:
                    where["type"] = type_filter
                if session:
                    where["session"] = session
                
                query_args = {"query_texts": [query], "n_results": top_k * 3}
                if where:
                    query_args["where"] = where if len(where) == 1 else {"$and": [{k: v} for k, v in where.items()]}
                
                vector_results = self.collection.query(**query_args)
                result_ids = vector_results["ids"][0] if vector_results["ids"] else []
                
                if result_ids:
                    placeholders = ",".join("?" for _ in result_ids)
                    with self._conn() as conn:
                        db_rows = conn.execute(f"SELECT * FROM memories WHERE id IN ({placeholders})", result_ids).fetchall()
                    
                    row_map = {r["id"]: dict(r) for r in db_rows}
                    scored = []
                    distances = vector_results.get("distances", [[0]*len(result_ids)])[0]
                    
                    for i, mem_id in enumerate(result_ids):
                        if mem_id in row_map:
                            row = row_map[mem_id]
                            row["score"] = self._compute_score(row["importance"], row["use_count"], row["last_used"])
                            if row["score"] > PRUNE_THRESHOLD:
                                distance = distances[i] if i < len(distances) else 1.0
                                similarity = 1.0 / (1.0 + distance)
                                combined = similarity * row["score"]
                                scored.append((combined, row))
                    
                    scored.sort(key=lambda x: x[0], reverse=True)
                    top_rows = [r for _, r in scored[:top_k]]
            except Exception as e:
                import logging
                logging.error(f"Vector search in episodic memory failed: {e}")
                
        if not top_rows:
            # Fallback a búsqueda basada en texto
            with self._conn() as conn:
                conditions = []
                params: list = []
                if type_filter:
                    conditions.append("type=?")
                    params.append(type_filter)
                if session:
                    conditions.append("session=?")
                    params.append(session)
                where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
                db_rows = conn.execute(f"SELECT * FROM memories {where}", params).fetchall()
                
            query_words = set(query.lower().split())
            scored = []
            for r in db_rows:
                d = dict(r)
                d["score"] = self._compute_score(d["importance"], d["use_count"], d["last_used"])
                if d["score"] > PRUNE_THRESHOLD:
                    content_lower = d["content"].lower()
                    hits = sum(1 for w in query_words if w in content_lower and len(w) > 2)
                    if hits > 0 or not query_words:
                        combined = (hits + 1) * d["score"]
                        scored.append((combined, d))
                        
            scored.sort(key=lambda x: x[0], reverse=True)
            top_rows = [r for _, r in scored[:top_k]]

        if not top_rows:
            return []

        # Registrar el uso de los recuerdos devueltos
        now = time.time()
        with self._conn() as conn:
            for row in top_rows:
                new_use = row["use_count"] + 1
                new_score = self._compute_score(row["importance"], new_use, now)
                conn.execute(
                    "UPDATE memories SET use_count=?, last_used=?, score=? WHERE id=?",
                    (new_use, now, new_score, row["id"]),
                )

        return [self._row_to_dict(r) for r in top_rows]

    def boost(self, memory_id: str, extra_importance: float = 0.5) -> Optional[dict]:
        """Aumenta manualmente la importancia de un recuerdo (lo ancla más tiempo)."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            if not row:
                return None
            now = time.time()
            new_imp = min(row["importance"] + extra_importance, 10.0)
            new_score = self._compute_score(new_imp, row["use_count"], now)
            conn.execute(
                "UPDATE memories SET importance=?, last_used=?, score=? WHERE id=?",
                (new_imp, now, new_score, memory_id),
            )
        return self.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
            deleted = cursor.rowcount > 0
            
        if deleted and self.collection is not None:
            try:
                self.collection.delete(ids=[memory_id])
            except Exception:
                pass
        return deleted

    def prune(self, threshold: float = PRUNE_THRESHOLD) -> int:
        """Elimina recuerdos cuyo score cayó por debajo del umbral calculándolo en SQL al vuelo. Devuelve cuántos borró."""
        deleted = 0
        ids_to_delete = []
        with self._conn() as conn:
            rows = conn.execute("SELECT id FROM memories WHERE compute_decay(importance, use_count, last_used) <= ?", (threshold,)).fetchall()
            ids_to_delete = [r["id"] for r in rows]
            
            if ids_to_delete:
                conn.executemany("DELETE FROM memories WHERE id=?", [(i,) for i in ids_to_delete])
                deleted = len(ids_to_delete)
                
        if deleted > 0 and self.collection is not None:
            try:
                for i in range(0, len(ids_to_delete), 5000):
                    self.collection.delete(ids=ids_to_delete[i:i+5000])
            except Exception as e:
                import logging
                logging.error(f"Error purging memory from ChromaDB: {e}")
                
        return deleted

    def stats(self) -> dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            by_type = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT type, COUNT(*) FROM memories GROUP BY type"
                ).fetchall()
            }
            sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            
            weak = conn.execute("SELECT COUNT(*) FROM memories WHERE compute_decay(importance, use_count, last_used) <= ?", (PRUNE_THRESHOLD,)).fetchone()[0]
        return {
            "total": total,
            "by_type": by_type,
            "ready_to_prune": weak,
            "sessions": sessions,
            "decay_half_life_days": DEFAULT_DECAY_HALF_LIFE_DAYS,
            "session_decay_days": SESSION_DECAY_DAYS,
        }

    # ───────────────────────────── Utils ───────────────────────────────── #

    def _session_to_dict(self, row) -> dict:
        if row is None:
            return {}
        d = dict(row)
        d["created_at_human"] = datetime.fromtimestamp(d["created_at"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        d["last_used_human"] = datetime.fromtimestamp(d["last_used"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        days_idle = (time.time() - d["last_used"]) / 86400
        d["days_idle"] = round(days_idle, 1)
        d["expires_in_days"] = round(max(0, SESSION_DECAY_DAYS - days_idle), 1)
        return d

    # ───────────────────────────── Utils ───────────────────────────────── #

    def _row_to_dict(self, row) -> dict:
        if row is None:
            return {}
        d = dict(row)
        # Formatear fechas legibles
        d["created_at_human"] = datetime.fromtimestamp(d["created_at"], tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        )
        d["last_used_human"] = datetime.fromtimestamp(d["last_used"], tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        )
        d["tags"] = d["tags"].split(",") if d["tags"] else []
        d["score"] = round(d["score"], 4)
        return d
