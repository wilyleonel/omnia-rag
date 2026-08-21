import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

import os
import yaml
import glob
import time
import hashlib
import sqlite3
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import chromadb
from chromadb.utils import embedding_functions
from ast_chunker import ASTChunker
import threading

# Configuración básica
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
CONFIG_FILE = os.path.join(BASE_DIR, "omnia.yaml")
DB_DIR = os.path.join(BASE_DIR, "data", "chroma_db")
SQLITE_DB = os.path.join(BASE_DIR, "data", "omnia_fts.sqlite")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"active_space": "default", "spaces": {"default": {"directories": []}}}
    with open(CONFIG_FILE, 'r') as f:
        config = yaml.safe_load(f) or {}
        
    if "directories" in config and "spaces" not in config:
        old_dirs = config.pop("directories")
        config["active_space"] = "default"
        config["spaces"] = {
            "default": {
                "directories": old_dirs
            }
        }
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(config, f)
            
    if "spaces" not in config:
        config["spaces"] = {"default": {"directories": []}}
    if "active_space" not in config:
        config["active_space"] = "default"
        
    return config

def make_chroma_client(config=None):
    """Crea el cliente de Chroma. Por defecto embebido (PersistentClient);
    si omnia.yaml define un bloque `chroma: {mode: http, host, port}` usa
    HttpClient contra un servidor Chroma separado (modo escalable opcional)."""
    cfg = (config or {}).get("chroma", {}) or {}
    if cfg.get("mode") == "http":
        return chromadb.HttpClient(
            host=cfg.get("host", "localhost"),
            port=cfg.get("port", 8001),
            settings=chromadb.Settings(anonymized_telemetry=False),
        )
    return chromadb.PersistentClient(path=DB_DIR, settings=chromadb.Settings(anonymized_telemetry=False))


DEFAULT_EXCLUDE_FILES = [
    "package-lock.json",
    "yarn.lock",
    "*.postman_collection.json",
    "*/locales/*",
    "*/postman/*",
    "*.min.js",
    "*.d.ts",
]


def should_index(filepath, dir_conf):
    """Filtro de archivo unico para el escaneo completo y para el watchdog."""
    import fnmatch

    if not any(filepath.endswith(ext) for ext in dir_conf.get("extensions", [])):
        return False

    for part in filepath.split(os.sep):
        if part in dir_conf.get("exclude", []):
            return False

    name = os.path.basename(filepath)
    for pattern in dir_conf.get("exclude_files", DEFAULT_EXCLUDE_FILES):
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(filepath, pattern):
            return False

    return True


def chunk_text(text, chunk_size=1000, overlap=200):
    """Chunking de fallback para archivos sin soporte AST (Markdown, JSON, texto plano).
    Agrupa por párrafos en vez de cortar por caracteres a ciegas; solo recurre al
    corte fijo cuando un párrafo individual excede chunk_size."""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            chunks.append(current)

        if len(para) <= chunk_size:
            current = para
        else:
            start = 0
            while start < len(para):
                end = start + chunk_size
                chunks.append(para[start:end])
                start += chunk_size - overlap
            current = ""

    if current:
        chunks.append(current)

    return [
        {"text": c, "symbol": "text_chunk", "type": "text", "start_line": 0, "end_line": 0}
        for c in chunks
    ]

class OmniaIndexer:
    def __init__(self, update_callback=None, chroma_client=None, embedding_function=None):
        self.config = load_config()
        self.client = chroma_client or make_chroma_client(self.config)
        self.ef = embedding_function or embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self.active_space = self.config.get("active_space", "default")

        # Ensure alphanumeric space names for SQLite/Chroma tables
        self.safe_space = "".join(c for c in self.active_space if c.isalnum() or c == "_") or "default"

        self.collection = self.client.get_or_create_collection(
            name=f"omnia_memory_{self.safe_space}",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )
        self.update_callback = update_callback
        self.ast_chunker = ASTChunker()
        self.db_lock = threading.Lock()
        # Evita que scan_all() y el watchdog reescriban la colección al mismo tiempo
        self.rebuild_lock = threading.RLock()
        self._init_sqlite()

    def get_directories(self):
        return self.config.get("spaces", {}).get(self.active_space, {}).get("directories", [])

    def set_active_space(self, space_name):
        self.config["active_space"] = space_name
        self.active_space = space_name
        self.safe_space = "".join(c for c in self.active_space if c.isalnum() or c == "_") or "default"
        self.collection = self.client.get_or_create_collection(
            name=f"omnia_memory_{self.safe_space}",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )
        self._init_sqlite()

    def _init_sqlite(self):
        self.conn = sqlite3.connect(SQLITE_DB, check_same_thread=False)
        with self.db_lock:
            cursor = self.conn.cursor()
            cursor.execute(f'''
                CREATE VIRTUAL TABLE IF NOT EXISTS omnia_search_{self.safe_space} 
                USING fts5(id, source, symbol, content, tokenize="trigram")
            ''')
            self.conn.commit()

    def reload_config(self):
        self.config = load_config()

    def get_file_hash(self, filepath):
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            buf = f.read()
            hasher.update(buf)
        return hasher.hexdigest()

    def remove_file(self, filepath):
        try:
            self.collection.delete(where={"source": filepath})
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute(f"DELETE FROM omnia_search_{self.safe_space} WHERE source = ?", (filepath,))
                self.conn.commit()
        except Exception as e:
            import logging
            logging.error(f"Error removing file {filepath}: {e}")

    def _get_stored_hash(self, filepath):
        """Hash guardado en Chroma para este archivo en la última indexación, si existe."""
        try:
            existing = self.collection.get(where={"source": filepath}, limit=1, include=["metadatas"])
            metas = existing.get("metadatas") or []
            if metas:
                return metas[0].get("hash")
        except Exception:
            pass
        return None

    def index_file(self, filepath, force=False):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            if not content.strip():
                return 0

            source_path = filepath
            file_hash = self.get_file_hash(filepath)

            if not force and self._get_stored_hash(filepath) == file_hash:
                return 0  # Sin cambios desde la última indexación: no reprocesar

            # Borrar chunks anteriores de este archivo
            self.remove_file(source_path)

            # 1. AST Chunker para GraphRAG (Nodos y Relaciones)
            ast_chunks = self.ast_chunker.chunk_file(filepath, content)
            
            # Fallback si el archivo no es soportado por AST
            if not ast_chunks:
                ast_chunks = chunk_text(content)
                
            documents, metadatas, ids = [], [], []
            sqlite_data = []
            
            # Llenar ChromaDB y SQLite simultáneamente
            for i, chunk in enumerate(ast_chunks):
                chunk_id = f"{source_path}_vector_{i}"
                
                # Para ChromaDB, si hay un summary, usamos eso. Si no, el text crudo.
                text_for_chroma = chunk.get("summary", chunk["text"])
                documents.append(text_for_chroma)
                
                # Armar metadata
                meta = {
                    "source": source_path, 
                    "hash": file_hash,
                    "symbol": chunk.get("symbol", "text_chunk"),
                    "type": chunk.get("type", "text"),
                    "start_line": chunk.get("start_line", 0),
                    "end_line": chunk.get("end_line", 0)
                }
                
                if "belongs_to" in chunk:
                    meta["belongs_to"] = chunk["belongs_to"]
                if "calls" in chunk:
                    meta["calls"] = ",".join(chunk["calls"])
                    
                metadatas.append(meta)
                ids.append(chunk_id)
                
                # Para SQLite, SIEMPRE guardamos el texto crudo para búsqueda exacta de código
                sqlite_data.append((f"{source_path}_fts_{i}", source_path, chunk.get("symbol", "text_chunk"), chunk["text"]))
                
            if documents:
                self.collection.add(documents=documents, metadatas=metadatas, ids=ids)

            if sqlite_data:
                try:
                    with self.db_lock:
                        cursor = self.conn.cursor()
                        cursor.executemany(
                            f"INSERT INTO omnia_search_{self.safe_space} (id, source, symbol, content) VALUES (?, ?, ?, ?)",
                            sqlite_data
                        )
                        self.conn.commit()
                except Exception:
                    # Revertir Chroma para no dejar los dos almacenes desincronizados
                    if documents:
                        try:
                            self.collection.delete(ids=ids)
                        except Exception:
                            pass
                    raise

            return len(documents)
        except Exception as e:
            import logging
            logging.error(f"Error indexing file {filepath}: {e}")
            return 0

    def purge_directory(self, dir_path):
        try:
            # Borrar de ChromaDB
            data = self.collection.get()
            ids_to_delete = [
                doc_id for doc_id, meta in zip(data["ids"], data["metadatas"]) 
                if meta["source"].startswith(dir_path)
            ]
            batch_size = 5000
            for i in range(0, len(ids_to_delete), batch_size):
                self.collection.delete(ids=ids_to_delete[i:i+batch_size])
                
            # Borrar de SQLite
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute(f"DELETE FROM omnia_search_{self.safe_space} WHERE source LIKE ?", (f"{dir_path}%",))
                self.conn.commit()
            
            return len(ids_to_delete)
        except Exception as e:
            import logging
            logging.error(f"Error purging directory {dir_path}: {e}")
            return 0

    def _reconcile_deleted(self, seen_sources, active_repos):
        """Borra del índice archivos que ya no existen o quedaron excluidos,
        sin tener que tirar y reconstruir toda la colección."""
        try:
            data = self.collection.get(include=["metadatas"])
        except Exception:
            return
        stale_sources = set()
        for meta in data.get("metadatas") or []:
            src = (meta or {}).get("source")
            if not src or src in seen_sources:
                continue
            if any(src.startswith(base) for base in active_repos):
                stale_sources.add(src)
        for src in stale_sources:
            self.remove_file(src)

    def scan_all(self):
        """Escaneo incremental: reindexa solo archivos nuevos/modificados
        (via hash, ver index_file) y reconcilia borrados. No destruye la
        colección existente en cada corrida."""
        total_docs = 0
        total_chunks = 0
        seen_sources = set()

        with self.rebuild_lock:
            active_repos = []
            for dir_conf in self.get_directories():
                path = os.path.abspath(os.path.join(BASE_DIR, dir_conf["path"]))
                if not os.path.exists(path):
                    continue

                active_repos.append(path)
                for root, dirs, files in os.walk(path):
                    dirs[:] = [d for d in dirs if d not in dir_conf.get("exclude", [])]

                    for file in files:
                        filepath = os.path.join(root, file)
                        if should_index(filepath, dir_conf):
                            seen_sources.add(filepath)
                            chunks_added = self.index_file(filepath)
                            if chunks_added > 0:
                                total_docs += 1
                                total_chunks += chunks_added

                                if self.update_callback:
                                    self.update_callback(documents=total_docs, chunks=total_chunks)

            self._reconcile_deleted(seen_sources, active_repos)

            try:
                final_chunk_count = self.collection.count()
            except Exception:
                final_chunk_count = total_chunks
            total_docs, total_chunks = len(seen_sources), final_chunk_count

        # === INYECCIÓN GRAPHIFY ===
        if active_repos:
            try:
                import subprocess
                print(f"Iniciando compilación de GraphRAG para {len(active_repos)} repositorios...")
                graphify_bin = os.path.join(BASE_DIR, "src", "graphify", "bin", "graphify-build.sh")
                graphify_core = os.path.join(BASE_DIR, "src", "graphify", "core", "graphify-core.sh")
                system_graph_dir = os.path.join(BASE_DIR, "system-graph", self.active_space)
                
                env = os.environ.copy()
                env["GRAPHIFY_BIN"] = graphify_core
                env["GRAPHIFY_SYSTEM_DIR"] = system_graph_dir
                
                # Ejecutar de manera no bloqueante (fire and forget)
                subprocess.Popen([graphify_bin] + active_repos, env=env)
                print("Compilación de GraphRAG lanzada en segundo plano.")
            except Exception as e:
                print(f"Error lanzando Graphify: {e}")
                
        return total_docs, total_chunks

class FileChangeHandler(FileSystemEventHandler):
    DEBOUNCE_SECONDS = 1.0

    def __init__(self, indexer):
        self.indexer = indexer
        self._last_event = {}
        self._debounce_lock = threading.Lock()

    def _is_debounced(self, filepath):
        now = time.time()
        with self._debounce_lock:
            last = self._last_event.get(filepath, 0)
            self._last_event[filepath] = now
            return (now - last) < self.DEBOUNCE_SECONDS

    def process(self, event, is_delete=False):
        if event.is_directory:
            return

        filepath = event.src_path
        if not is_delete and self._is_debounced(filepath):
            return

        for dir_conf in self.indexer.get_directories():
            base_path = os.path.abspath(os.path.join(BASE_DIR, dir_conf["path"]))
            if filepath.startswith(base_path):
                if should_index(filepath, dir_conf):
                    with self.indexer.rebuild_lock:
                        if is_delete:
                            self.indexer.remove_file(filepath)
                        else:
                            self.indexer.index_file(filepath)
                    break

    def on_modified(self, event):
        self.process(event)

    def on_created(self, event):
        self.process(event)
        
    def on_deleted(self, event):
        self.process(event, is_delete=True)

def start_watchdog(indexer):
    observer = Observer()
    handler = FileChangeHandler(indexer)
    
    for dir_conf in indexer.get_directories():
        path = os.path.abspath(os.path.join(BASE_DIR, dir_conf["path"]))
        if os.path.exists(path):
            observer.schedule(handler, path, recursive=True)
            
    observer.start()
    return observer
