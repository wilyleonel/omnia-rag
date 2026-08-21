import math
import time

from memory import MemoryStore, DECAY_RATE


def compute_score(importance, use_count, last_used):
    # _compute_score no usa self, solo DECAY_RATE (constante de módulo),
    # así que se puede invocar sin instanciar MemoryStore (que requiere
    # sqlite/chroma reales en __init__).
    return MemoryStore._compute_score(None, importance, use_count, last_used)


def test_score_decays_over_time():
    now = time.time()
    fresh = compute_score(1.0, 1, now)
    old = compute_score(1.0, 1, now - 30 * 86400)
    assert old < fresh


def test_score_scales_with_importance_and_use_count():
    now = time.time()
    base = compute_score(1.0, 1, now)
    more_important = compute_score(2.0, 1, now)
    more_used = compute_score(1.0, 5, now)
    assert more_important > base
    assert more_used > base


def test_score_matches_formula_exactly():
    now = time.time()
    last_used = now - 10 * 86400
    expected = (3.0 * 4) * math.exp(-DECAY_RATE * 10)
    assert math.isclose(compute_score(3.0, 4, last_used), expected, rel_tol=1e-6)
