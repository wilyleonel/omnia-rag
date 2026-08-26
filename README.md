# Omnia-RAG 🧠⚡

**Omnia-RAG** es un sistema local de Inteligencia Artificial que transforma cualquier repositorio de código y base de conocimiento en una única memoria semántica ultrarrápida. Actúa como un "cerebro auxiliar" que intercepta consultas para alimentar IAs (como Claude, Cursor, o ChatGPT) con contexto matemático preciso, reduciendo dramáticamente el consumo de tokens.

---

## 🌟 ¿Por qué Omnia-RAG?

Cuando inyectas cientos de archivos manualmente a un LLM:
1. Gasto excesivo de tokens (💸).
2. El modelo sufre de *context-bloat* y pierde precisión (😵‍💫).
3. Tiempo de latencia inaceptable para desarrolladores rápidos (🐢).

**Con Omnia-RAG:**
- **Latencia Cero:** Responde en ~0.05 segundos porque el modelo vive en memoria.
- **100% Privado y Local:** El código nunca se envía a OpenAI para generar embeddings.
- **Ahorro en Tiempo Real:** El dashboard en terminal calcula cuánto dinero ahorraste al evitar enviar código irrelevante.

---

## 🛠️ Tech Stack (Tecnologías Utilizadas)

Este proyecto no es "solo un script de Python", es una arquitectura robusta:

- **HuggingFace Sentence-Transformers (`all-MiniLM-L6-v2`):** El "Cerebro Lector". Un modelo LLM local superligero que convierte tu código en rayos matemáticos de 384 dimensiones (Embeddings). **100% Local y Privado**.
- **ChromaDB:** La "Biblioteca Vectorial". Base de datos especializada en IA que usa HNSW para buscar similitud semántica en milisegundos.
- **FastAPI + Uvicorn:** El "Backend Asíncrono". Servidor web ultrarrápido para mantener los modelos cargados en memoria RAM y evitar arranques en frío.
- **Watchdog:** El "Observador". Vigila tu código en tiempo real y actualiza *solo el fragmento modificado* en ChromaDB (Actualizaciones incrementales).
- **Three.js / 3D-Force-Graph:** El "Visualizador Espacial". Renderiza el mapa semántico de tu código en 3D usando WebGL (agrupando por jerarquía y similitud vectorial).
- **Rich:** UI interactiva en la terminal (Dashboard de ahorros).

---

## 📁 Estructura del Proyecto

```text
Omnia-RAG/
├── omnia.yaml                # Configuración: Define qué carpetas indexar
├── requirements.txt          # Dependencias
├── src/
│   ├── core/
│   │   ├── indexer.py        # Indexación incremental y File Watcher
│   │   ├── server.py         # Servidor FastAPI
│   │   ├── dashboard.py      # Interfaz de terminal con métricas
│   │   └── visualizer.py     # Generador de Mapa Semántico 3D
│   └── adapters/
│       ├── claude_hook.py    # Hook para inyectar contexto en Claude CLI
│       └── generic_client.py # Cliente genérico consumible por cualquier script
```

---

## 🚀 Cómo Empezar

### 1. Instalación
Clona el repositorio e instala las dependencias del motor RAG en Python y del servidor MCP en Node.js:

```bash
git clone https://github.com/wilyleonel/omnia-rag.git
cd omnia-rag

# 1. Instalar dependencias del motor RAG (Python)
# NOTA IMPORTANTE SOBRE VERSIONES: El proyecto usa versiones específicas (ChromaDB 1.5.9+, 
# Sentence-Transformers 6.0.0+, Numpy 2.0.0+) para asegurar compatibilidad con Python 3.14+
pip install -r requirements.txt

# 2. Instalar dependencias del Servidor MCP (Node.js)
cd mcp-server
npm install
cd ..

# 3. (Opcional pero Recomendado) Crear comando global
# Añade este alias a tu terminal para escanear desde cualquier carpeta
echo "alias omnia-scanner='python3 $(pwd)/src/core/server.py'" >> ~/.zshrc
source ~/.zshrc
```

### 2. Ejecutar y Escanear (El Nuevo Comando Mágico ✨)
Ya no necesitas editar `omnia.yaml` manualmente para configurar rutas. Gracias al alias, puedes pararte en **cualquier proyecto** y arrancar el servidor directamente allí:

```bash
# 1. Entra a la carpeta de tu proyecto
cd /Users/willy/Documents/MiProyectoWeb

# 2. Ejecuta el comando (escanea la carpeta actual automáticamente)
omnia-scanner
```

*(El servidor detectará tu ubicación, actualizará su configuración por detrás, indexará tu código, y se quedará escuchando cambios en segundo plano).*

---

### Módulo Visualizador 🌌
¿Quieres ver tu código como una galaxia de datos interconectados?
```bash
python src/core/visualizer.py
```
Abre el archivo `espacio_vectorial.html` generado y navega por tu arquitectura.
# omnia-rag
<img width="1504" height="779" alt="image" src="https://github.com/user-attachments/assets/3bbde4e7-b496-4054-b93e-56a4cc1eaf28" />
