"""Búsqueda híbrida (vector + FTS5) con fusión Reciprocal Rank Fusion (RRF).

Extraído del endpoint /buscar de server.py para poder testearse sin
levantar FastAPI/Chroma/embeddings reales (ver tests/test_search_rrf.py).
"""
import re
import logging

RRF_K = 60

# Umbral mínimo de score RRF para descartar resultados de relevancia marginal.
# Antes solo lo aplicaba claude_hook.py del lado del cliente; ahora se aplica
# server-side para que todos los consumidores (MCP, generic_client, etc.)
# reciban el mismo filtro sin duplicarlo.
MIN_RESULT_SCORE = 0.012


def hybrid_search(indexer, q: str, n: int = 5, min_score: float = MIN_RESULT_SCORE):
    """Ejecuta búsqueda vectorial (Chroma) + texto exacto (SQLite FTS5) y
    fusiona ambos rankings con RRF. Es bloqueante: se debe llamar vía
    asyncio.to_thread desde una ruta async."""
    vector_results = indexer.collection.query(query_texts=[q], n_results=n * 2)

    fts_results = []
    try:
        safe_q = re.sub(r'[^\w\s]', ' ', q)
        fts_query = " OR ".join(f'"{word}"' for word in safe_q.split() if len(word) > 2)
        if not fts_query:
            fts_query = f'"{safe_q.strip()}"'

        cursor = indexer.conn.cursor()
        table = f"omnia_search_{indexer.safe_space}"
        cursor.execute(f'''
            SELECT id, source, symbol, content
            FROM {table}
            WHERE {table} MATCH ?
            ORDER BY rank
            LIMIT ?
        ''', (fts_query, n * 2))
        fts_results = cursor.fetchall()
    except Exception as e:
        logging.error(f"FTS5 Error: {e}")

    scores = {}
    docs_metadata = {}

    if vector_results["ids"] and vector_results["ids"][0]:
        for rank, doc_id in enumerate(vector_results["ids"][0]):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (RRF_K + rank + 1)
            docs_metadata[doc_id] = {
                "text": vector_results["documents"][0][rank],
                "meta": vector_results["metadatas"][0][rank],
                "source": "vector"
            }

    for rank, row in enumerate(fts_results):
        doc_id, source, symbol, content = row
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        if doc_id not in docs_metadata:
            docs_metadata[doc_id] = {
                "text": content,
                "meta": {"source": source, "symbol": symbol, "type": "fts"},
                "source": "exact"
            }

    ranked_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    final_results = []
    for doc_id, score in ranked_docs:
        if score < min_score:
            continue
        doc_info = docs_metadata[doc_id]
        final_results.append({
            "id": doc_id,
            "text": doc_info["text"],
            "metadata": doc_info["meta"],
            "score": round(score, 4),
            "match_type": doc_info["source"]
        })
        if len(final_results) >= n:
            break

    return final_results
