import threading

from search import hybrid_search, RRF_K


class FakeCollection:
    """Emula collection.query(...) de ChromaDB devolviendo resultados fijos."""

    def __init__(self, ids, documents, metadatas):
        self._ids = ids
        self._documents = documents
        self._metadatas = metadatas

    def query(self, query_texts, n_results):
        return {
            "ids": [self._ids[:n_results]],
            "documents": [self._documents[:n_results]],
            "metadatas": [self._metadatas[:n_results]],
        }


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, sql, params):
        pass

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return FakeCursor(self._rows)


class FakeIndexer:
    def __init__(self, vector_ids, vector_docs, vector_metas, fts_rows):
        self.collection = FakeCollection(vector_ids, vector_docs, vector_metas)
        self.conn = FakeConn(fts_rows)
        self.safe_space = "default"
        self.db_lock = threading.Lock()


def test_hybrid_search_merges_vector_and_fts_results():
    indexer = FakeIndexer(
        vector_ids=["a", "b"],
        vector_docs=["texto vectorial a", "texto vectorial b"],
        vector_metas=[{"source": "a.py"}, {"source": "b.py"}],
        fts_rows=[("c", "c.py", "func_c", "texto exacto c")],
    )

    results = hybrid_search(indexer, "algo", n=5, min_score=0.0)

    ids = [r["id"] for r in results]
    assert "a" in ids and "b" in ids and "c" in ids
    assert all(r["score"] > 0 for r in results)


def test_hybrid_search_ranks_doc_found_in_both_sources_higher():
    indexer = FakeIndexer(
        vector_ids=["a", "b"],
        vector_docs=["texto a", "texto b"],
        vector_metas=[{"source": "a.py"}, {"source": "b.py"}],
        fts_rows=[("a", "a.py", "func_a", "texto a")],
    )

    results = hybrid_search(indexer, "algo", n=5, min_score=0.0)

    assert results[0]["id"] == "a"
    expected_a_score = round(1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 1), 4)
    assert results[0]["score"] == expected_a_score


def test_hybrid_search_respects_min_score_threshold():
    indexer = FakeIndexer(
        vector_ids=["a"],
        vector_docs=["texto a"],
        vector_metas=[{"source": "a.py"}],
        fts_rows=[],
    )

    results = hybrid_search(indexer, "algo", n=5, min_score=1.0)

    assert results == []


def test_hybrid_search_respects_n_limit():
    indexer = FakeIndexer(
        vector_ids=["a", "b", "c"],
        vector_docs=["ta", "tb", "tc"],
        vector_metas=[{"source": "a.py"}, {"source": "b.py"}, {"source": "c.py"}],
        fts_rows=[],
    )

    results = hybrid_search(indexer, "algo", n=2, min_score=0.0)

    assert len(results) == 2
