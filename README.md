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
Clona el repositorio e instala las dependencias:
```bash
git clone https://github.com/tu-usuario/Omnia-RAG.git
cd Omnia-RAG
pip install -r requirements.txt
```

### python3 src/core/server.py


### 2. Configuración
Copia o edita el archivo `omnia.yaml` para añadir las rutas a tu código y notas (Soporta múltiples repositorios).

### 3. Ejecutar
Arranca el sistema:
```bash
python3 src/core/server.py
```
*(El servidor indexará tu código automáticamente, abrirá el Dashboard y se quedará escuchando cambios).*

---

### Módulo Visualizador 🌌
¿Quieres ver tu código como una galaxia de datos interconectados?
```bash
python src/core/visualizer.py
```
Abre el archivo `espacio_vectorial.html` generado y navega por tu arquitectura.
# omnia-rag
