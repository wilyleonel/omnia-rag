# Regla de Integración Omnia-RAG (MCP)

Cualquier asistente de IA que trabaje en este repositorio debe cumplir las siguientes directivas:

1. **Conexión Obligatoria a Omnia-RAG vía MCP:**
   - Para cualquier consulta de contexto, análisis de código, búsqueda de funciones o explicación de arquitectura, la IA **debe conectarse obligatoriamente mediante MCP (Model Context Protocol)** al servidor de Omnia-RAG (`node mcp-server/index.js`).

2. **Indexación y Lectura de `README.md`:**
   - La IA debe priorizar la lectura e indexación de los archivos `README.md` y documentación Markdown para identificar rápidamente el propósito del repositorio y la ubicación de los módulos clave.
