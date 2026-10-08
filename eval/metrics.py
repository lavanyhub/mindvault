"""Retrieval quality metrics for eval/evaluate_retrieval.py.

Kept dependency-free (just stdlib math) since these are simple enough not
to need numpy/sklearn, and it's one fewer thing to explain in an interview.
"""

import math


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Fraction of relevant chunks that appear in the top-k retrieved."""
    if not relevant_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    hits = len(top_k & relevant_ids)
    return hits / len(relevant_ids)


def reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """1 / rank of the first relevant chunk found, 0 if none found."""
    for rank, cid in enumerate(retrieved_ids, start=1):
        if cid in relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Binary-relevance nDCG@k: relevant chunk = gain 1, else 0."""
    if not relevant_ids:
        return 0.0

    dcg = 0.0
    for i, cid in enumerate(retrieved_ids[:k]):
        if cid in relevant_ids:
            dcg += 1.0 / math.log2(i + 2)  # i is 0-indexed, rank = i+1

    ideal_hits = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    if idcg == 0:
        return 0.0
    return dcg / idcg


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0
