# Omnia-RAG 🧠⚡
> **Local-first codebase RAG with semantic indexing, local embeddings, MCP (Model Context Protocol) and token-efficient context retrieval.**

**Omnia-RAG** es un sistema local de Inteligencia Artificial que transforma cualquier repositorio de código y base de conocimiento en una única memoria semántica ultrarrápida. Actúa como un "cerebro auxiliar" que intercepta consultas para alimentar IAs (como Claude, Cursor, ChatGPT o agentes MCP) con contexto matemático preciso, reduciendo dramáticamente el consumo de tokens.

---

## 🔑 Key Features & Keywords (Palabras Clave)
- **Local-first Codebase RAG:** Búsqueda semántica 100% privada sin enviar tu código a la nube.
- **Codebase Indexing & Semantic Search:** Indexación AST inteligente de funciones, clases y módulos.
- **Model Context Protocol (MCP):** Integración nativa con asistentes como Claude Desktop, Cursor y agentes autónomos.
- **Token-Efficient Context Retrieval:** Recupera solo los fragmentos relevantes para evitar el *context-bloat* y ahorrar tokens.
- **Local Embeddings:** Basado en `sentence-transformers` (`all-MiniLM-L6-v2`) y **ChromaDB**.

---

## 🌟 ¿Por qué Omnia-RAG?

Cuando inyectas cientos de archivos manualmente a un LLM:
1. Gasto excesivo de tokens (💸).
2. El modelo sufre de *context-bloat* y pierde precisión (😵‍💫).
3. Tiempo de latencia inaceptable para desarrolladores rápidos (🐢).

**Con Omnia-RAG:**
- **Latencia Cero:** Responde en ~0.05 segundos porque el modelo vive en memoria RAM.
- **100% Privado y Local:** El código nunca se envía a OpenAI u otros proveedores para generar embeddings.
- **Ahorro en Tiempo Real:** El dashboard en terminal calcula cuánto dinero ahorraste al evitar enviar código irrelevante.

---

## 🛠️ Tech Stack (Tecnologías Utilizadas)

- **HuggingFace Sentence-Transformers (`all-MiniLM-L6-v2`):** El "Cerebro Lector". Un modelo LLM local superligero que convierte tu código en vectores de 384 dimensiones (Embeddings). **100% Local y Privado**.
- **ChromaDB:** La "Biblioteca Vectorial". Base de datos especializada en IA que usa HNSW para buscar similitud semántica en milisegundos.
- **FastAPI + Uvicorn:** El "Backend Asíncrono". Servidor web ultrarrápido para mantener los modelos cargados en RAM y evitar arranques en frío.
- **Watchdog:** El "Observador". Vigila tu código en tiempo real y actualiza *solo el fragmento modificado* en ChromaDB (Actualizaciones incrementales).
- **Three.js / 3D-Force-Graph:** El "Visualizador Espacial". Renderiza el mapa semántico de tu código en 3D usando WebGL.
- **MCP (Model Context Protocol):** Servidor Node.js para comunicación estándar con clientes de IA.

---

## 📁 Estructura del Proyecto

```text
Omnia-RAG/
├── omnia.yaml                # Configuración: Define qué carpetas indexar
├── requirements.txt          # Dependencias Python (ChromaDB, Transformers, FastAPI)
├── src/
│   ├── core/
│   │   ├── indexer.py        # Indexación incremental y File Watcher
│   │   ├── server.py         # Servidor FastAPI
│   │   ├── dashboard.py      # Interfaz de terminal con métricas
│   │   └── visualizer.py     # Generador de Mapa Semántico 3D
│   └── adapters/
│       └── claude_hook.py    # Hook para inyectar contexto en Claude CLI
├── mcp-server/               # Servidor MCP en Node.js (stdio)
│   └── index.js
└── .agents/                  # Reglas y Skills para Agentes IA
    ├── rules/
    └── skills/
```

---

## 🚀 Cómo Empezar

### 1. Instalación
Clona el repositorio e instala las dependencias del motor RAG en Python y del servidor MCP en Node.js:

```bash
git clone https://github.com/wilyleonel/omnia-rag.git
cd omnia-rag

# 1. Crear entorno e instalar dependencias Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Instalar dependencias del Servidor MCP (Node.js)
cd mcp-server
npm install
cd ..

# 3. Crear comando global (opcional)
echo "alias omnia-scanner='$(pwd)/.venv/bin/python3 $(pwd)/src/core/server.py'" >> ~/.zshrc
source ~/.zshrc
```

### 2. Ejecutar y Escanear
Puedes pararte en **cualquier proyecto** y arrancar el servidor directamente allí:

```bash
cd /Ruta/A/Tu/Proyecto
omnia-scanner
```

---

## 🤖 Integración MCP para Agentes de IA

Para conectar Omnia-RAG con **Claude Desktop**, **Cursor** o agentes **Antigravity**, añade esta configuración MCP:

```json
{
  "mcpServers": {
    "omnia-rag": {
      "command": "node",
      "args": [
        "/Ruta/Absoluta/A/omnia-rag/mcp-server/index.js"
      ]
    }
  }
}
```

---

## 🌌 Módulo Visualizador 3D
¿Quieres ver tu código como una galaxia de datos interconectados?
```bash
python src/core/visualizer.py
```
Abre el archivo `espacio_vectorial.html` generado y navega por tu arquitectura.

<img width="1504" height="779" alt="Visualizador 3D Omnia-RAG" src="https://github.com/user-attachments/assets/3bbde4e7-b496-4054-b93e-56a4cc1eaf28" />

---

## 🏷️ Recomendación de GitHub Topics

Para maximizar la descubribilidad de este repositorio en las búsquedas de GitHub, configura los siguientes **Topics** en los ajustes principales del repositorio:

`rag` | `codebase-rag` | `code-indexing` | `semantic-search` | `mcp` | `model-context-protocol` | `local-embeddings` | `vector-database` | `chromadb` | `token-optimization` | `ai-memory`
