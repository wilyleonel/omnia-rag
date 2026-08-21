#!/usr/bin/env python3
"""Purga quirurgica: borra ruido y huerfanos sin reindexar.

Uso:  python3 purge_noise.py --dry-run   (solo reporta)
      python3 purge_noise.py             (borra)

REQUIERE el servidor parado: ChromaDB no admite dos procesos.
"""
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

import sys
import fnmatch
import sqlite3
import shutil
import yaml
import chromadb
from chromadb.utils import embedding_functions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB = os.path.join(BASE_DIR, "data", "omnia_fts.sqlite")
DB_DIR = os.path.join(BASE_DIR, "data", "chroma_db")
DRY = "--dry-run" in sys.argv

config = yaml.safe_load(open(os.path.join(BASE_DIR, "omnia.yaml")))
space = config.get("active_space", "default")
safe_space = "".join(c for c in space if c.isalnum() or c == "_") or "default"
dirs = config["spaces"][space]["directories"]
patterns = dirs[0].get("exclude_files", []) if dirs else []


def is_noise(path):
    if "/locales/" in path:
        return True
    name = os.path.basename(path)
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(path, p) for p in patterns)


def is_orphan(path):
    return not os.path.exists(path)


conn = sqlite3.connect(SQLITE_DB)
table = f"omnia_search_{safe_space}"

rows = conn.execute(f"SELECT id, source FROM {table}").fetchall()
noise = {i for i, s in rows if is_noise(s)}
orphan = {i for i, s in rows if is_orphan(s)}
doomed = noise | orphan

print(f"tabla activa : {table}  ({len(rows)} chunks)")
print(f"  ruido      : {len(noise)}")
print(f"  huerfanos  : {len(orphan)}")
print(f"  a borrar   : {len(doomed)}")

# Tabla FTS residual de una version anterior: nadie la mantiene.
legacy = conn.execute(
    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='omnia_search'"
).fetchone()[0]
legacy_rows = 0
if legacy and table != "omnia_search":
    legacy_rows = conn.execute("SELECT count(*) FROM omnia_search").fetchone()[0]
    print(f"tabla legacy : omnia_search ({legacy_rows} chunks) -> DROP")

if DRY:
    print("\n[dry-run] nada modificado")
    sys.exit(0)

backup = SQLITE_DB + ".prepurge"
if not os.path.exists(backup):
    print(f"\nbackup sqlite -> {backup}")
    shutil.copy2(SQLITE_DB, backup)

cur = conn.cursor()
for i in range(0, len(doomed), 500):
    batch = list(doomed)[i:i + 500]
    cur.execute(
        f"DELETE FROM {table} WHERE id IN ({','.join('?' * len(batch))})", batch
    )
if legacy and table != "omnia_search":
    cur.execute("DROP TABLE IF EXISTS omnia_search")
conn.commit()

print("compactando sqlite (VACUUM)...")
conn.execute("VACUUM")
conn.close()

print("limpiando ChromaDB...")
client = chromadb.PersistentClient(
    path=DB_DIR, settings=chromadb.Settings(anonymized_telemetry=False)
)
ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
col = client.get_or_create_collection(name=f"omnia_memory_{safe_space}", embedding_function=ef)

data = col.get(include=["metadatas"])
kill = [
    doc_id
    for doc_id, meta in zip(data["ids"], data["metadatas"])
    if meta and meta.get("source") and (is_noise(meta["source"]) or is_orphan(meta["source"]))
]
for i in range(0, len(kill), 5000):
    col.delete(ids=kill[i:i + 5000])

print(f"chroma: {len(kill)} borrados, quedan {col.count()}")
print(f"sqlite: {len(doomed)} borrados" + (f" + tabla legacy ({legacy_rows})" if legacy_rows else ""))
print("\nListo. Arranca el servidor: python3 src/core/server.py")
