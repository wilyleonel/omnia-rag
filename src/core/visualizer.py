import os
import json
import chromadb
# Configuración básica
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
DB_DIR = os.path.join(BASE_DIR, "data", "chroma_db")

def generate_graph_data(collection=None, limit=1200, microservice=None):
    if collection is None:
        return {"nodes": [], "links": []}
        
    print("🌌 Omnia-RAG Visualizer: Generando Grafo AST (Nivel 2)...")
    
    try:
        # Ya no necesitamos embeddings, solo metadatos
        data = collection.get(include=["metadatas"])
    except Exception:
        print("La colección no existe aún.")
        return {"nodes": [], "links": []}
        
    if not data or not data["metadatas"]:
        print("No hay datos suficientes para graficar.")
        return {"nodes": [], "links": []}
        
    metadatas = data['metadatas']

    nodes = []
    links = []
    
    # Mapeo rápido para buscar nodos por símbolo (para enlazar las llamadas)
    symbol_to_id = {}
    valid_node_ids = set()
    
    # 1. Crear Nodos
    for meta in metadatas:
        source = meta.get("source", "Unknown")
        symbol = meta.get("symbol", "Unknown")
        node_type = meta.get("type", "text")
        
        # Ignorar los bloques de texto plano
        if symbol == "text_chunk" or node_type == "text":
            continue
            
        # Tampoco renderizar Interfaces y Tipos (DTOs) en el visualizador 3D
        if node_type in ["interface_declaration", "type_alias_declaration"]:
            continue
            
        # Ignorar específicamente clases que son DTOs
        if "dto" in symbol.lower() or "dto" in source.lower() or ".dto." in source.lower():
            continue
            
        # El ID único del nodo
        node_id = f"{source}::{symbol}"
        
        # Solo lo necesario: si se pide un microservicio, descartar el resto ya aqui
        if microservice and f"/{microservice}/" not in source:
            continue

        # Evitar nodos con id repetido (rompen el mapeo del grafo)
        if node_id in valid_node_ids:
            continue

        # Guardamos en diccionario
        symbol_to_id[symbol] = node_id
        valid_node_ids.add(node_id)
        
        # Tamaño según importancia
        val = 1.0
        if node_type == "class":
            val = 4.0
        elif node_type == "function":
            val = 2.0
            
        # El grupo para el color
        nodes.append({
            "id": node_id,
            "name": f"{symbol}",
            "group": node_type,
            "val": val,
            "source": source
        })

    print(f"Generados {len(nodes)} Nodos AST. Trazando enlaces...")

    # Set temporal para evitar enlaces duplicados A->B
    existing_links = set()

    # 2. Crear Enlaces (Edges)
    for meta in metadatas:
        source = meta.get("source", "Unknown")
        symbol = meta.get("symbol", "Unknown")
        source_id = f"{source}::{symbol}"
        
        # Si el nodo origen fue ignorado (ej. es un DTO), no le sacamos flechas
        if source_id not in valid_node_ids:
            continue
            
        # Enlaces Estructurales (belongs_to)
        belongs_to = meta.get("belongs_to")
        if belongs_to and belongs_to in symbol_to_id:
            target_id = symbol_to_id[belongs_to]
            if target_id in valid_node_ids and source_id != target_id:
                link_key = f"{source_id}->{target_id}"
                if link_key not in existing_links:
                    links.append({
                        "source": source_id,
                        "target": target_id,
                        "val": 1.5,
                        "type": "structural"
                    })
                    existing_links.add(link_key)
        
        # Enlaces de Comportamiento (calls)
        calls_str = meta.get("calls", "")
        if calls_str:
            calls_list = [c.strip() for c in calls_str.split(",") if c.strip()]
            for call in calls_list:
                parts = call.split('.')
                last_part = parts[-1]
                
                target_id = None
                
                if call in symbol_to_id:
                    target_id = symbol_to_id[call]
                elif last_part in symbol_to_id:
                    target_id = symbol_to_id[last_part]
                
                if target_id and target_id in valid_node_ids and source_id != target_id:
                    link_key = f"{source_id}->{target_id}"
                    if link_key not in existing_links:
                        links.append({
                            "source": source_id,
                            "target": target_id,
                            "val": 0.5,
                            "type": "call"
                        })
                        existing_links.add(link_key)

    # 3. Limpiar enlaces rotos (nodos que fueron ignorados como DTOs)
    kept = {n["id"] for n in nodes}
    links = [l for l in links if l["source"] in kept and l["target"] in kept]

    # 4. Poda: renderizar solo lo necesario.
    # Con miles de nodos el layout no converge y la escena queda ilegible,
    # asi que nos quedamos con los mas conectados (los que explican la arquitectura).
    if limit and len(nodes) > limit:
        degree = {}
        for l in links:
            degree[l["source"]] = degree.get(l["source"], 0) + 1
            degree[l["target"]] = degree.get(l["target"], 0) + 1

        nodes.sort(key=lambda n: (degree.get(n["id"], 0), n["val"]), reverse=True)
        nodes = nodes[:limit]
        kept = {n["id"] for n in nodes}
        links = [l for l in links if l["source"] in kept and l["target"] in kept]
        print(f"Podado a {len(nodes)} nodos / {len(links)} enlaces (limit={limit}).")

    return {"nodes": nodes, "links": links}

if __name__ == "__main__":
    data = generate_graph_data()
    if data:
        print(f"Grafo generado con {len(data['nodes'])} nodos y {len(data['links'])} conexiones.")
