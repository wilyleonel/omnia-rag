#!/usr/bin/env node

const { Server } = require("@modelcontextprotocol/sdk/server/index.js");
const { StdioServerTransport } = require("@modelcontextprotocol/sdk/server/stdio.js");
const { CallToolRequestSchema, ListToolsRequestSchema } = require("@modelcontextprotocol/sdk/types.js");

const server = new Server(
  {
    name: "omnia-rag-mcp",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Listar herramientas
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "search_omnia_rag",
        description: "Busca en la base de código local usando el motor avanzado de Omnia-RAG. Útil para encontrar funciones exactas, clases, o contexto de archivos a través de múltiples microservicios.",
        inputSchema: {
          type: "object",
          properties: {
            query: {
              type: "string",
              description: "La palabra, función, o frase a buscar (ej. 'realPrice' o 'verifyDeposit').",
            },
          },
          required: ["query"],
        },
      },
      {
        name: "graphify_impact_analysis",
        description: "Analiza el radio de impacto estructural de modificar un archivo o función específica. Te dice qué otros archivos, funciones o repositorios dependen directa o indirectamente de él.",
        inputSchema: {
          type: "object",
          properties: {
            file: {
              type: "string",
              description: "El nombre del archivo o función a analizar (ej. 'middleware.ts' o 'verifyDeposit').",
            },
          },
          required: ["file"],
        },
      },
      {
        name: "graphify_shortest_path",
        description: "Encuentra el camino más corto de dependencias (imports/calls) entre dos componentes de la arquitectura.",
        inputSchema: {
          type: "object",
          properties: {
            source: {
              type: "string",
              description: "Componente de origen (ej. 'AuthModule').",
            },
            target: {
              type: "string",
              description: "Componente de destino (ej. 'Database').",
            },
          },
          required: ["source", "target"],
        },
      },
      {
        name: "graphify_god_nodes",
        description: "Devuelve los 'Nodos Dios' del sistema: los archivos o funciones más altamente acoplados y conectados de toda la arquitectura multi-repositorio.",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
    ],
  };
});

// Manejar llamadas a herramientas
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  if (request.params.name === "search_omnia_rag") {
    const query = request.params.arguments.query;
    try {
      const baseUrl = process.env.OMNIA_API_URL || "http://127.0.0.1:8000";
      // Hacer petición HTTP al servidor de Omnia-RAG local (FastAPI)
      const res = await fetch(`${baseUrl}/buscar?q=${encodeURIComponent(query)}`);
      
      if (!res.ok) {
        throw new Error(`Error del servidor: ${res.status}`);
      }
      
      const data = await res.json();
      
      if (!data.results || data.results.length === 0) {
        return {
          content: [
            {
              type: "text",
              text: `No se encontraron resultados en Omnia-RAG para: "${query}"`,
            },
          ],
        };
      }

      let resultText = `=== Resultados Omnia-RAG para "${query}" ===\n\n`;
      
      data.results.forEach((r, i) => {
        const meta = r.metadata || {};
        resultText += `[Resultado ${i + 1}] Archivo: ${meta.source}\n`;
        if (meta.symbol && meta.symbol !== "text_chunk") {
            resultText += `Símbolo (AST): ${meta.symbol}\n`;
        }
        resultText += `--- Código ---\n${r.text}\n`;
        resultText += `----------------------------------------\n\n`;
      });

      return {
        content: [
          {
            type: "text",
            text: resultText,
          },
        ],
      };
    } catch (error) {
      return {
        content: [
          {
            type: "text",
            text: `Error conectando con Omnia-RAG. Asegúrate de que el servidor esté corriendo. Detalles: ${error.message}`,
          },
        ],
        isError: true,
      };
    }
  } else if (request.params.name === "graphify_impact_analysis") {
    try {
      const baseUrl = process.env.OMNIA_API_URL || "http://127.0.0.1:8000";
      const res = await fetch(`${baseUrl}/api/graphify/impact?file=${encodeURIComponent(request.params.arguments.file)}`);
      const data = await res.json();
      return { content: [{ type: "text", text: data.output || data.error }] };
    } catch (e) {
      return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
    }
  } else if (request.params.name === "graphify_shortest_path") {
    try {
      const baseUrl = process.env.OMNIA_API_URL || "http://127.0.0.1:8000";
      const res = await fetch(`${baseUrl}/api/graphify/path?source=${encodeURIComponent(request.params.arguments.source)}&target=${encodeURIComponent(request.params.arguments.target)}`);
      const data = await res.json();
      return { content: [{ type: "text", text: data.output || data.error }] };
    } catch (e) {
      return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
    }
  } else if (request.params.name === "graphify_god_nodes") {
    try {
      const baseUrl = process.env.OMNIA_API_URL || "http://127.0.0.1:8000";
      const res = await fetch(`${baseUrl}/api/graphify/god_nodes`);
      const data = await res.json();
      return { content: [{ type: "text", text: data.output || data.error }] };
    } catch (e) {
      return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true };
    }
  }

  throw new Error("Tool no encontrada");
});

// Iniciar servidor MCP por stdio
async function run() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Omnia-RAG MCP Server corriendo en stdio");
}

run().catch((error) => {
  console.error("Error fatal en el servidor MCP:", error);
  process.exit(1);
});
