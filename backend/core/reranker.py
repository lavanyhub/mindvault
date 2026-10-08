"""Cross-encoder reranking for retrieved chunks.

UPGRADE (Phase 2.4): retriever.py fuses vector + BM25 results with RRF,
which is good at merging two ranked lists but still ranks purely on
bi-encoder similarity / keyword overlap — neither actually reads the
query and the chunk together. A cross-encoder scores (query, chunk)
pairs jointly, which is far more accurate but too slow to run over an
entire corpus. So it's used only to rerank the small top-N candidate
set RRF already narrowed down, not for first-pass retrieval.

Loaded lazily and cached at module level so the ~90MB model is only
loaded once per process, not once per request.
"""

import logging

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder
        logger.info("Loading cross-encoder model (first use, may take a moment)...")
        _model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _model


def rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """Rerank candidate chunks by (query, chunk) relevance.

    candidates: list of dicts each with at least a 'content' key.
    Returns the top_k candidates, each with a 'rerank_score' key added,
    sorted descending by that score.

    Falls back to returning the first top_k candidates unchanged if the
    cross-encoder can't be loaded (e.g. sentence-transformers missing or
    no network access to download the model on first run) — degrades to
    RRF-only ranking rather than breaking retrieval entirely.
    """
    if not candidates:
        return []

    try:
        model = _get_model()
    except Exception:
        logger.exception("Cross-encoder unavailable, skipping rerank")
        return candidates[:top_k]

    pairs = [(query, c["content"]) for c in candidates]
    scores = model.predict(pairs)

    scored = list(zip(candidates, scores))
    scored.sort(key=lambda pair: pair[1], reverse=True)

    results = []
    for candidate, score in scored[:top_k]:
        item = dict(candidate)
        item["rerank_score"] = float(score)
        results.append(item)
    return results
