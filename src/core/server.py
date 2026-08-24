import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

import sys
import yaml
import threading
import time
import uvicorn
import asyncio
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, BackgroundTasks
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
from typing import Optional, List
from pydantic import BaseModel
from memory import MemoryStore
from indexer import OmniaIndexer, start_watchdog, make_chroma_client, load_config as load_indexer_config, EMBEDDING_MODEL_NAME
from search import hybrid_search, MIN_RESULT_SCORE
from chromadb.utils import embedding_functions

logging.basicConfig(level=logging.INFO)

from dashboard import Dashboard
from rich.live import Live

# Intervalo de purga automática de memoria episódica (decay + sesiones inactivas)
PRUNE_INTERVAL_SECONDS = 6 * 3600


async def _periodic_prune(app: FastAPI):
    """Corre en background durante toda la vida del proceso: purga recuerdos
    con score de decay caído y sesiones inactivas cada PRUNE_INTERVAL_SECONDS."""
    while True:
        try:
            await asyncio.sleep(PRUNE_INTERVAL_SECONDS)
            memory_store = getattr(app.state, 'memory_store', None)
            if memory_store:
                removed = await asyncio.to_thread(memory_store.prune)
                pruned_sessions = await asyncio.to_thread(memory_store.session_prune_old)
                logging.info(f"Prune periódico: {len(removed)} recuerdos, {len(pruned_sessions)} sesiones")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"Error en prune periódico: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialización
    app.state.dashboard = Dashboard()
    app.state.is_syncing = False
    app.state.current_indexed_chunks = 0
    
    def on_indexer_update(documents, chunks):
        app.state.current_indexed_chunks = chunks

    app.state.sync_lock = threading.Lock()

    # Iniciar cliente de Chroma y Embedding de forma global compartida
    # (make_chroma_client respeta un bloque opcional `chroma: {mode: http, ...}`
    # en omnia.yaml; por defecto usa el PersistentClient embebido de siempre)
    app.state.chroma_client = make_chroma_client(load_indexer_config())
    app.state.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL_NAME)

    app.state.indexer = OmniaIndexer(
        update_callback=on_indexer_update,
        chroma_client=app.state.chroma_client,
        embedding_function=app.state.embedding_function
    )
    app.state.memory_store = MemoryStore(
        db_path=MEMORY_DB_PATH,
        chroma_client=app.state.chroma_client,
        embedding_function=app.state.embedding_function,
        indexer=app.state.indexer,
    )
    
    # Cargar contadores
    try:
        docs = app.state.indexer.collection.count()
    except Exception:
        docs = 0
    app.state.dashboard.update_stats(documents=docs, chunks=docs)

    # Arrancar watchdog
    app.state.watchdog_observer = start_watchdog(app.state.indexer)

    # Purga periódica de memoria episódica (decay) en background
    app.state.prune_task = asyncio.create_task(_periodic_prune(app))

    yield

    # Cleanup
    if hasattr(app.state, 'watchdog_observer') and app.state.watchdog_observer:
        app.state.watchdog_observer.stop()
        app.state.watchdog_observer.join()

    if hasattr(app.state, 'prune_task') and app.state.prune_task:
        app.state.prune_task.cancel()
        try:
            await app.state.prune_task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="Omnia-RAG Backend", lifespan=lifespan)

# Omnia-RAG corre local (127.0.0.1) por defecto, pero el dashboard web puede
# servirse desde otro origen (ej. Vite dev server) durante desarrollo.
ALLOWED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Token opcional: si se define OMNIA_API_TOKEN en el entorno, todas las
# rutas /api/*, /buscar, /memory y /sessions exigen ese token vía header
# `X-Omnia-Token`. Sin la variable definida (caso por defecto, uso local),
# no se exige nada — mantiene el comportamiento actual sin romper nada.
API_TOKEN = os.environ.get("OMNIA_API_TOKEN")


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if API_TOKEN and request.url.path not in ("/", "/ws") and not request.url.path.startswith("/public"):
        if request.headers.get("X-Omnia-Token") != API_TOKEN:
            return JSONResponse(status_code=401, content={"detail": "Token inválido o ausente"})
    return await call_next(request)


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
MEMORY_DB_PATH = os.path.join(BASE_DIR, "data", "memory.sqlite")
CONFIG_FILE = os.path.join(BASE_DIR, "omnia.yaml")
PUBLIC_DIR = os.path.join(BASE_DIR, "src", "public")
CONFIG_LOCK = threading.Lock()


def read_config():
    """Lee omnia.yaml de forma centralizada, protegido contra escrituras concurrentes."""
    with CONFIG_LOCK:
        with open(CONFIG_FILE, 'r') as f:
            return yaml.safe_load(f) or {}


def write_config(config):
    """Escribe omnia.yaml de forma centralizada, protegido contra escrituras concurrentes."""
    with CONFIG_LOCK:
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(config, f)


if not os.path.exists(PUBLIC_DIR):
    os.makedirs(PUBLIC_DIR)

app.mount("/public", StaticFiles(directory=PUBLIC_DIR), name="public")

class Workspace(BaseModel):
    path: str

class SpaceUpdate(BaseModel):
    name: str


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)



@app.get("/")
def read_root():
    # If index.html exists, serve it. Otherwise return a basic message.
    idx_path = os.path.join(PUBLIC_DIR, "index.html")
    if os.path.exists(idx_path):
        return FileResponse(idx_path)
    return {"message": "index.html not found in public directory."}

@app.get("/api/graph")
def get_graph(request: Request, limit: int = 1200, ms: str = ""):
    from visualizer import generate_graph_data
    indexer = getattr(request.app.state, 'indexer', None)
    if not indexer or not hasattr(indexer, 'collection'):
        return {"nodes": [], "links": []}
    return generate_graph_data(indexer.collection, limit=limit, microservice=ms or None)


@app.get("/api/microservices")
def get_microservices(request: Request):
    """Lista los microservicios indexados, para poder cargar solo uno."""
    indexer = getattr(request.app.state, 'indexer', None)
    if not indexer or not hasattr(indexer, 'collection'):
        return {"microservices": []}
    try:
        data = request.app.state.indexer.collection.get(include=["metadatas"])
    except Exception:
        return {"microservices": []}

    bases = [os.path.abspath(os.path.join(BASE_DIR, d["path"])) for d in request.app.state.indexer.get_directories()]
    found = {}
    for meta in data.get("metadatas") or []:
        src = (meta or {}).get("source") or ""
        for b in bases:
            if src.startswith(b):
                rel = src[len(b):].lstrip(os.sep)
                name = rel.split(os.sep)[0]
                if name:
                    found[name] = found.get(name, 0) + 1
                break
    ordered = sorted(found.items(), key=lambda x: x[1], reverse=True)
    return {"microservices": [{"name": n, "chunks": c} for n, c in ordered]}

@app.get("/api/spaces")
def get_spaces(request: Request):
    config = request.app.state.indexer.config
    spaces = list(config.get("spaces", {}).keys())
    return {"active": request.app.state.indexer.active_space, "spaces": spaces}

@app.post("/api/spaces")
def create_space(request: Request, space: SpaceUpdate):
    config = read_config()

    if "spaces" not in config:
        config["spaces"] = {}

    if space.name in config["spaces"]:
        raise HTTPException(status_code=400, detail="Space already exists")

    config["spaces"][space.name] = {"directories": []}

    write_config(config)

    request.app.state.indexer.reload_config()
    return {"message": "Space created"}

@app.put("/api/spaces/active")
def set_active_space(request: Request, space: SpaceUpdate):
    config = read_config()

    if space.name not in config.get("spaces", {}):
        raise HTTPException(status_code=404, detail="Space not found")

    config["active_space"] = space.name

    write_config(config)

    request.app.state.indexer.reload_config()
    request.app.state.indexer.set_active_space(space.name)
    
    
    if hasattr(request.app.state, 'watchdog_observer') and request.app.state.watchdog_observer:
        request.app.state.watchdog_observer.stop()
        request.app.state.watchdog_observer.join()
    request.app.state.watchdog_observer = start_watchdog(request.app.state.indexer)
    
    return {"message": f"Active space changed to {space.name}"}

@app.get("/api/workspaces")
def get_workspaces(request: Request):
    return request.app.state.indexer.get_directories()

@app.get("/api/select-folder")
async def select_folder():
    def get_folder():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        # Bring window to front
        try:
            root.attributes('-topmost', True)
        except Exception:
            pass
        folder = filedialog.askdirectory(title="Selecciona la carpeta del proyecto para añadir a Omnia-RAG")
        root.destroy()
        return folder

    try:
        folder_path = await asyncio.to_thread(get_folder)
        if folder_path:
            return {"path": folder_path}
    except Exception as e:
        pass
        
    return {"path": ""}

@app.post("/api/workspaces")
async def add_workspace(request: Request, ws: Workspace):

    # Mismo guard que /api/refresh: sin esto, un add_workspace concurrente
    # con un refresh_all (o con otro add_workspace) dispara dos scan_all()
    # en paralelo, ambos escribiendo sobre el mismo Chroma/SQLite.
    if request.app.state.is_syncing:
        raise HTTPException(status_code=409, detail="Ya hay una sincronización en curso")

    # Sanity check mínimo: sin esto, cualquier string llega a omnia.yaml y
    # recién se descubre que el path no sirve cuando scan_all() no indexa
    # nada. No es un allowlist de raíces permitidas (este es un tool local
    # de un solo usuario), solo evita guardar basura.
    full_path = os.path.abspath(os.path.join(BASE_DIR, ws.path))
    if not os.path.isdir(full_path):
        raise HTTPException(status_code=400, detail=f"El path no existe o no es un directorio: {full_path}")

    config = read_config()

    active = request.app.state.indexer.active_space
    if "spaces" not in config:
        config["spaces"] = {active: {"directories": []}}
    if active not in config["spaces"]:
        config["spaces"][active] = {"directories": []}

    directories = config["spaces"][active].get("directories", [])

    if any(d["path"] == ws.path for d in directories):
        raise HTTPException(status_code=400, detail="Workspace already exists")

    directories.append({
        "path": ws.path,
        "extensions": [".ts", ".tsx", ".md", ".json", ".js", ".py"],
        "exclude": ["node_modules", "dist", "build", ".git", ".claude", "venv", "__pycache__", ".next"]
    })

    config["spaces"][active]["directories"] = directories

    write_config(config)

    request.app.state.indexer.reload_config()

    def _scan():
        with request.app.state.sync_lock:
            try:
                request.app.state.is_syncing = True
                return request.app.state.indexer.scan_all()
            finally:
                request.app.state.is_syncing = False

    docs, chunks = await asyncio.to_thread(_scan)
    request.app.state.dashboard.update_stats(documents=docs, chunks=chunks)

    if hasattr(request.app.state, 'watchdog_observer') and request.app.state.watchdog_observer:
        request.app.state.watchdog_observer.stop()
        request.app.state.watchdog_observer.join()
    request.app.state.watchdog_observer = start_watchdog(request.app.state.indexer)
    
    return {"message": "Workspace added successfully", "directories": request.app.state.indexer.get_directories()}

@app.delete("/api/workspaces")
async def delete_workspace(request: Request, ws: Workspace):

    config = read_config()

    active = request.app.state.indexer.active_space
    directories = config.get("spaces", {}).get(active, {}).get("directories", [])

    original_len = len(directories)
    directories = [d for d in directories if d["path"] != ws.path]

    if len(directories) == original_len:
        raise HTTPException(status_code=404, detail="Workspace not found")

    config["spaces"][active]["directories"] = directories

    write_config(config)

    full_path = os.path.abspath(os.path.join(BASE_DIR, ws.path))
    await asyncio.to_thread(request.app.state.indexer.purge_directory, full_path)
    
    request.app.state.indexer.reload_config()
    
    if hasattr(request.app.state, 'watchdog_observer') and request.app.state.watchdog_observer:
        request.app.state.watchdog_observer.stop()
        request.app.state.watchdog_observer.join()
    request.app.state.watchdog_observer = start_watchdog(request.app.state.indexer)
    
    return {"message": "Workspace deleted successfully", "directories": request.app.state.indexer.get_directories()}

@app.get("/api/graphify/impact")
async def graphify_impact(request: Request, file: str):
    import subprocess
    graphify_query = os.path.join(BASE_DIR, "src", "graphify", "core", "graphify-query.sh")
    system_graph = os.path.join(BASE_DIR, "system-graph", request.app.state.indexer.active_space, "graph.json")
    env = os.environ.copy()
    env["GRAPHIFY_GRAPH"] = system_graph
    
    try:
        result = await asyncio.to_thread(subprocess.run, [graphify_query, "impact", file], env=env, capture_output=True, text=True)
        await manager.broadcast({"type": "activity_update"})
        return {"output": result.stdout if result.stdout else result.stderr}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/graphify/path")
async def graphify_path(request: Request, source: str, target: str):
    import subprocess
    graphify_query = os.path.join(BASE_DIR, "src", "graphify", "core", "graphify-query.sh")
    system_graph = os.path.join(BASE_DIR, "system-graph", request.app.state.indexer.active_space, "graph.json")
    env = os.environ.copy()
    env["GRAPHIFY_GRAPH"] = system_graph
    
    try:
        result = await asyncio.to_thread(subprocess.run, [graphify_query, "path", source, target], env=env, capture_output=True, text=True)
        await manager.broadcast({"type": "activity_update"})
        return {"output": result.stdout if result.stdout else result.stderr}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/graphify/god_nodes")
async def graphify_god_nodes(request: Request):
    import subprocess
    graphify_query = os.path.join(BASE_DIR, "src", "graphify", "core", "graphify-query.sh")
    system_graph = os.path.join(BASE_DIR, "system-graph", request.app.state.indexer.active_space, "graph.json")
    env = os.environ.copy()
    env["GRAPHIFY_GRAPH"] = system_graph
    
    try:
        result = await asyncio.to_thread(subprocess.run, [graphify_query, "god-nodes"], env=env, capture_output=True, text=True)
        await manager.broadcast({"type": "activity_update"})
        return {"output": result.stdout if result.stdout else result.stderr}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/activity")

def get_activity(request: Request):
    activity_file = os.path.join(BASE_DIR, "system-graph", request.app.state.indexer.active_space, "activity.json")
    if not os.path.exists(activity_file):
        return {"type": None, "nodes": []}
    
    # Check if the file is older than 10 seconds
    mtime = os.path.getmtime(activity_file)
    if time.time() - mtime > 10:
        return {"type": None, "nodes": []}
        
    try:
        with open(activity_file, "r") as f:
            data = json.load(f)
            return data
    except Exception:
        return {"type": None, "nodes": []}


@app.post("/api/refresh")
async def refresh_all(request: Request, background_tasks: BackgroundTasks):
    
    if request.app.state.is_syncing:
        return {"message": "Ya hay una sincronización en curso"}
        
    def run_sync():
        with request.app.state.sync_lock:
            try:
                request.app.state.is_syncing = True
                request.app.state.current_indexed_chunks = 0
                docs, chunks = request.app.state.indexer.scan_all()
                request.app.state.dashboard.update_stats(documents=docs, chunks=chunks)
                request.app.state.current_indexed_chunks = chunks
            finally:
                request.app.state.is_syncing = False

    background_tasks.add_task(run_sync)
    return {"message": "Sincronización iniciada en segundo plano"}

@app.get("/api/status")
def get_status(request: Request):
    if not request.app.state.indexer:
        return {"status": "offline"}
    
    if request.app.state.is_syncing:
        return {"status": "syncing", "documents_indexed": request.app.state.current_indexed_chunks}
    else:
        try:
            docs = request.app.state.indexer.collection.count()
        except Exception:
            docs = request.app.state.current_indexed_chunks
        return {"status": "idle", "documents_indexed": docs}


@app.get("/api/dashboard", summary="Estadísticas agregadas para el panel web")
def get_dashboard(request: Request):
    dashboard = getattr(request.app.state, 'dashboard', None)
    if not dashboard:
        return {}
    return dashboard.stats


@app.get("/buscar")
async def buscar(request: Request, q: str, n: int = 5, min_score: float = MIN_RESULT_SCORE):
    indexer = getattr(request.app.state, 'indexer', None)
    if not indexer or not indexer.collection.count():
        return {"results": []}

    final_results = await asyncio.to_thread(hybrid_search, indexer, q, n, min_score)

    # Log semantic search activity
    activity_file = os.path.join(BASE_DIR, "system-graph", request.app.state.indexer.active_space, "activity.json")
    try:
        os.makedirs(os.path.dirname(activity_file), exist_ok=True)
        with open(activity_file, "w") as f:
            import json
            nodes = [r["id"] for r in final_results]
            json.dump({"type": "semantic-search", "nodes": nodes}, f)
    except Exception as e:
        print(f"Error logging activity: {e}")

    await manager.broadcast({"type": "activity_update"})

    current_queries = request.app.state.dashboard.stats["queries_today"] + 1
    current_tokens = request.app.state.dashboard.stats["tokens_avoided"] + sum(len(r["text"])//4 for r in final_results)
    request.app.state.dashboard.update_stats(queries_today=current_queries, tokens_avoided=current_tokens)
    
    return {"results": final_results}


# ═══════════════════════════════════════════════════════════
#  MEMORIA EPISÓDICA  — endpoints
# ═══════════════════════════════════════════════════════════

class MemoryIn(BaseModel):
    content: str
    type: str = "insight"          # rule | pattern | insight | decision | context
    tags: List[str] = []
    importance: float = 1.0        # 1.0 normal, 2.0 importante, 5.0 crítico
    session: str = "global"        # sesión a la que pertenece

class BoostIn(BaseModel):
    extra_importance: float = 0.5

class SessionIn(BaseModel):
    name: str
    description: str = ""


@app.post("/memory", summary="Guarda un recuerdo")
async def memory_add(request: Request, body: MemoryIn):
    if not request.app.state.memory_store:
        raise HTTPException(503, "Memory store no inicializado")
    mem = await asyncio.to_thread(
        request.app.state.memory_store.add,
        content=body.content,
        type=body.type,
        tags=body.tags,
        importance=body.importance,
        session=body.session,
        space=request.app.state.indexer.active_space,
    )
    return {"ok": True, "memory": mem}


@app.get("/memory/recall", summary="Busca recuerdos relevantes (sin session=busca en todo; space=* busca en todos los workspaces)")
async def memory_recall(request: Request, q: str, top_k: int = 5, type: Optional[str] = None, session: Optional[str] = None, space: Optional[str] = None):
    if not request.app.state.memory_store:
        raise HTTPException(503, "Memory store no inicializado")
    # Por defecto, solo recuerdos del workspace activo (evita que un recuerdo
    # guardado en otro space "se filtre" al contexto de este). space="*" para
    # buscar explícitamente en todos los workspaces.
    effective_space = None if space == "*" else (space or request.app.state.indexer.active_space)
    results = await asyncio.to_thread(
        request.app.state.memory_store.recall, query=q, top_k=top_k, type_filter=type, session=session, space=effective_space
    )
    return {"results": results, "count": len(results)}


@app.get("/memory", summary="Lista recuerdos (filtra por sesión/space opcional; space=* lista todos los workspaces)")
async def memory_list(request: Request, limit: int = 50, type: Optional[str] = None, session: Optional[str] = None, space: Optional[str] = None):
    if not request.app.state.memory_store:
        raise HTTPException(503, "Memory store no inicializado")
    effective_space = None if space == "*" else (space or request.app.state.indexer.active_space)
    mems = await asyncio.to_thread(
        request.app.state.memory_store.list_all, limit=limit, type_filter=type, session=session, space=effective_space
    )
    return {"memories": mems}


@app.post("/memory/{memory_id}/boost", summary="Aumenta la importancia de un recuerdo")
async def memory_boost(request: Request, memory_id: str, body: BoostIn):
    if not request.app.state.memory_store:
        raise HTTPException(503, "Memory store no inicializado")
    mem = await asyncio.to_thread(request.app.state.memory_store.boost, memory_id, body.extra_importance)
    if not mem:
        raise HTTPException(404, f"Recuerdo '{memory_id}' no encontrado")
    return {"ok": True, "memory": mem}


@app.delete("/memory/{memory_id}", summary="Elimina un recuerdo manualmente")
async def memory_delete(request: Request, memory_id: str):
    if not request.app.state.memory_store:
        raise HTTPException(503, "Memory store no inicializado")
    deleted = await asyncio.to_thread(request.app.state.memory_store.delete, memory_id)
    if not deleted:
        raise HTTPException(404, f"Recuerdo '{memory_id}' no encontrado")
    return {"ok": True, "deleted": memory_id}


@app.post("/memory/prune", summary="Purga recuerdos con score caído (decay automático)")
async def memory_prune(request: Request, threshold: float = 0.05):
    if not request.app.state.memory_store:
        raise HTTPException(503, "Memory store no inicializado")
    removed = await asyncio.to_thread(request.app.state.memory_store.prune, threshold)
    return {"ok": True, "pruned": removed}


@app.get("/memory/stats", summary="Estadísticas del sistema de memoria")
async def memory_stats(request: Request):
    if not request.app.state.memory_store:
        raise HTTPException(503, "Memory store no inicializado")
    stats = await asyncio.to_thread(request.app.state.memory_store.stats)
    return stats


# ═══════════════════════════════════════════════════════════
#  SESIONES  — endpoints
# ═══════════════════════════════════════════════════════════

@app.post("/sessions", summary="Crea o recupera una sesión por nombre")
async def session_create(request: Request, body: SessionIn):
    if not request.app.state.memory_store:
        raise HTTPException(503, "Memory store no inicializado")
    session = await asyncio.to_thread(
        request.app.state.memory_store.session_create, name=body.name, description=body.description
    )
    return {"ok": True, "session": session}


@app.get("/sessions", summary="Lista todas las sesiones con sus estadísticas")
async def session_list(request: Request):
    if not request.app.state.memory_store:
        raise HTTPException(503, "Memory store no inicializado")
    sessions = await asyncio.to_thread(request.app.state.memory_store.session_list)
    return {"sessions": sessions}


@app.post("/sessions/{name}/touch", summary="Marca la sesión como usada ahora (resetea su decay)")
async def session_touch(request: Request, name: str):
    if not request.app.state.memory_store:
        raise HTTPException(503, "Memory store no inicializado")
    ok = await asyncio.to_thread(request.app.state.memory_store.session_touch, name)
    if not ok:
        raise HTTPException(404, f"Sesión '{name}' no encontrada")
    return {"ok": True, "session": name, "message": "Decay reseteado"}


@app.delete("/sessions/{name}", summary="Elimina una sesión y todas sus memorias")
async def session_delete(request: Request, name: str):
    if not request.app.state.memory_store:
        raise HTTPException(503, "Memory store no inicializado")
    try:
        result = await asyncio.to_thread(request.app.state.memory_store.session_delete, name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, **result}


@app.post("/sessions/prune", summary="Purga sesiones inactivas y sus memorias")
async def session_prune(request: Request, days: int = 30):
    if not request.app.state.memory_store:
        raise HTTPException(503, "Memory store no inicializado")
    pruned = await asyncio.to_thread(request.app.state.memory_store.session_prune_old, days=days)
    return {"ok": True, "pruned": pruned, "count": len(pruned)}


if __name__ == "__main__":
    print("Iniciando Omnia-RAG Backend en http://localhost:8000 ...")
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info", access_log=False)
