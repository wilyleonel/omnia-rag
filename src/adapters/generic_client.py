import requests

# Cliente Genérico de Omnia-RAG
# Puedes usar este script como base para conectar Omnia a tu propio código
# o interfaz de IA personalizada.

OMNIA_URL = "http://127.0.0.1:8000/buscar"

def fetch_context(query: str, max_results: int = 3):
    print(f"Buscando en Omnia-RAG: '{query}'...\n")
    try:
        response = requests.get(f"{OMNIA_URL}?q={query}&n={max_results}", timeout=2.0)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("results"):
            print("No se encontraron resultados relevantes.")
            return

        for i, result in enumerate(data["results"]):
            source = result["metadata"]["source"]
            print(f"[{i+1}] Archivo: {source}")
            print("-" * 40)
            print(result["text"].strip())
            print("=" * 40 + "\n")
            
    except requests.exceptions.RequestException as e:
        print(f"Error conectando al servidor Omnia: {e}")

if __name__ == "__main__":
    pregunta = input("¿Qué necesitas buscar en tu código? ")
    fetch_context(pregunta)
