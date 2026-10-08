"""Hybrid retrieval: vector search + BM25 keyword search, fused with RRF,
then reranked with a cross-encoder.

UPGRADE (Phase 2): routes.py used to call vector_store.search() directly
and call the result "hybrid" without ever combining it with keyword
search — this file is what makes that claim true. Pipeline:

  1. Vector search (ChromaDB, via embedder.VectorStore.search)
  2. Keyword search (SQLite FTS5 over chunks_fts, BM25-ranked)
  3. Reciprocal Rank Fusion of the two ranked lists (k=60 — this exact
     RRF implementation was written and unit-tested standalone during
     the earlier bug-fix pass, before wiring it in here)
  4. Cross-encoder rerank of the fused top candidates down to top_k
     (core/reranker.py)
"""

import logging
from database import db_cursor
from core import reranker

logger = logging.getLogger(__name__)

RRF_K = 60
FUSION_CANDIDATES = 20  # how many each side contributes before fusion
RERANK_TOP_K = 5


def _keyword_search(query: str, top_k: int = FUSION_CANDIDATES) -> list[dict]:
    """BM25 search over chunks_fts.

    FIX carried over from the earlier whole-document FTS5 search: MATCH
    syntax treats punctuation as query operators, so a query containing a
    stray quote or colon raises 'fts5: syntax error'. Falls back to a
    quoted phrase search, which escapes those characters.
    """
    def run(match_query):
        with db_cursor() as conn:
            return conn.execute('''
                SELECT chunk_id, doc_id, title, content, bm25(chunks_fts) AS rank
                FROM chunks_fts
                WHERE chunks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            ''', (match_query, top_k)).fetchall()

    try:
        rows = run(query)
    except Exception:
        quoted = '"' + query.replace('"', '""') + '"'
        try:
            rows = run(quoted)
        except Exception:
            logger.exception("chunks_fts search failed even with quoted fallback")
            return []

    return [
        {
            'chunk_id': r['chunk_id'],
            'doc_id': r['doc_id'],
            'title': r['title'],
            'content': r['content'],
            # bm25() is lower-is-better; flip the sign so "higher is
            # better" holds across both retrieval methods, matching the
            # vector side's cosine 'score'.
            'score': -r['rank'],
        }
        for r in rows
    ]


def _vector_search(query: str, vector_store, top_k: int = FUSION_CANDIDATES) -> list[dict]:
    return vector_store.search(query, top_k=top_k)


def _fusion_key(item: dict) -> str:
    """Identify 'the same chunk' across the two result lists.

    Keyword results carry the real chunk_id (doc_{id}_chunk_{i}) written
    at ingestion time in routes.py. Vector results only carry
    doc_id/title/content — Chroma's query response doesn't surface the
    chunk index — so for those the content text is the only stable
    identifier available. Both indexes are built from the exact same
    chunk strings at ingestion, so this reliably matches the same chunk
    across both lists in practice.
    """
    return item.get('chunk_id') or f"content::{item['content']}"


def reciprocal_rank_fusion(result_lists: list[list[dict]], k: int = RRF_K) -> list[dict]:
    """Merge multiple ranked lists into one, ranking items found by
    multiple methods highest — without normalizing cosine similarity
    against BM25, which sit on incomparable scales.

    RRF_score(d) = sum over lists i containing d of 1 / (k + rank_i(d)),
    rank_i being the 1-indexed position of d in list i.
    """
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}

    for result_list in result_lists:
        for rank, item in enumerate(result_list, start=1):
            key = _fusion_key(item)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in items:
                items[key] = item

    fused = [
        {**items[key], 'rrf_score': round(score, 6)}
        for key, score in scores.items()
    ]
    fused.sort(key=lambda x: x['rrf_score'], reverse=True)
    return fused


def hybrid_search(query: str, vector_store) -> dict:
    """Full pipeline: retrieve from both methods, fuse, rerank.

    Keeps returning the raw vector/keyword lists alongside the new fused
    'results' key so the frontend's existing response shape doesn't break.
    """
    vector_results = _vector_search(query, vector_store)
    keyword_results = _keyword_search(query)

    fused = reciprocal_rank_fusion([vector_results, keyword_results])
    reranked = reranker.rerank(query, fused[:FUSION_CANDIDATES], top_k=RERANK_TOP_K)

    return {
        'results': reranked,
        'vector_results': vector_results,
        'keyword_results': keyword_results,
    }


def retrieve_for_answer(question: str, vector_store, top_k: int = RERANK_TOP_K) -> list[dict]:
    """Same pipeline as hybrid_search, collapsed to just the chunks a
    downstream LLM answer should be grounded in.
    """
    result = hybrid_search(question, vector_store)
    return result['results'][:top_k]
