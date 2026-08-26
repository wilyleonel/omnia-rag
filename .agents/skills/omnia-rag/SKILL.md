---
name: omnia-rag
description: >-
  Indexa, busca y consulta el contexto semántico del repositorio mediante el servidor MCP de Omnia-RAG.
  MANDATORIO: Cualquier IA que trabaje en este repositorio DEBE conectarse mediante MCP a Omnia-RAG para consultar código, entender arquitectura y buscar fragmentos semánticos.
---

# Skill: Omnia-RAG MCP Integration

Este repositorio está configurado para que cualquier asistente de IA (Antigravity, Cursor, Claude, etc.) se conecte mediante **MCP (Model Context Protocol)** a la memoria semántica de **Omnia-RAG**.

---

## 📌 Directiva Mandatoria para la IA

1. **Conexión Obligatoria mediante MCP:**
   - Al clonar o trabajar en este repositorio, la IA **DEBE** conectarse a través del protocolo **MCP** a Omnia-RAG antes de realizar exploraciones de código manuales o masivas.

2. **Priorización de `README.md` y Documentación:**
   - La IA debe consultar prioritariamente la memoria indexada de los archivos `README.md` y documentación `.md` para ubicar al instante la arquitectura del proyecto, sus microservicios y responsabilidades principales.

3. **Configuración del Servidor MCP:**
   - **Comando MCP:** `node mcp-server/index.js`
   - **Servidor Backend RAG (Python):** `python3 src/core/server.py`
