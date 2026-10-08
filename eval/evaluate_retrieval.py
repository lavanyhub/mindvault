"""Phase 3.2 — retrieval quality across four configurations.

Runs every question in eval/golden_set.json through:
    A. Vector only          (current pre-upgrade baseline)
    B. BM25 only             (chunks_fts, unfused)
    C. Hybrid + RRF          (fused, no rerank)
    D. Hybrid + RRF + rerank (the full Phase 2 pipeline)

and reports Recall@{1,3,5,10}, MRR, nDCG@5, and mean latency per config.
The A->D delta across these is the actual evidence behind "hybrid
retrieval with reranking improves recall" — a claim that meant nothing
before this file existed.

Usage:
    cd backend && python ../eval/evaluate_retrieval.py
    cd backend && python ../eval/evaluate_retrieval.py --golden-set ../eval/golden_set.draft.json
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.dirname(__file__))

from core.embedder import VectorStore  # noqa: E402
from core import retriever  # noqa: E402
from core import reranker  # noqa: E402
import metrics  # noqa: E402

K_VALUES = [1, 3, 5, 10]
RETRIEVE_TOP_K = 10  # retrieve enough to score Recall@10


def load_golden_set(path: str) -> list[dict]:
    if not os.path.exists(path):
        example = os.path.join(os.path.dirname(__file__), 'golden_set.example.json')
        raise FileNotFoundError(
            f"{path} not found.\n"
            f"Run 'python build_golden_set.py' against your own uploaded "
            f"documents first (see eval/build_golden_set.py), or start from "
            f"the schema in {example}."
        )
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def config_a_vector_only(question: str, vector_store) -> list[str]:
    results = vector_store.search(question, top_k=RETRIEVE_TOP_K)
    return [retriever._fusion_key(r) for r in results]


def config_b_bm25_only(question: str) -> list[str]:
    results = retriever._keyword_search(question, top_k=RETRIEVE_TOP_K)
    return [retriever._fusion_key(r) for r in results]


def config_c_hybrid_rrf(question: str, vector_store) -> list[str]:
    vector_results = retriever._vector_search(question, vector_store, top_k=RETRIEVE_TOP_K)
    keyword_results = retriever._keyword_search(question, top_k=RETRIEVE_TOP_K)
    fused = retriever.reciprocal_rank_fusion([vector_results, keyword_results])
    return [retriever._fusion_key(r) for r in fused[:RETRIEVE_TOP_K]]


def config_d_hybrid_rrf_rerank(question: str, vector_store) -> list[str]:
    vector_results = retriever._vector_search(question, vector_store, top_k=RETRIEVE_TOP_K)
    keyword_results = retriever._keyword_search(question, top_k=RETRIEVE_TOP_K)
    fused = retriever.reciprocal_rank_fusion([vector_results, keyword_results])
    reranked = reranker.rerank(question, fused[:RETRIEVE_TOP_K], top_k=RETRIEVE_TOP_K)
    return [retriever._fusion_key(r) for r in reranked]


def evaluate_config(name: str, fn, golden_set: list[dict]) -> dict:
    per_question = {f'recall@{k}': [] for k in K_VALUES}
    per_question['mrr'] = []
    per_question['ndcg@5'] = []
    latencies = []

    for item in golden_set:
        relevant = set(item.get('relevant_chunk_ids') or [])
        if not relevant:
            # negative-category questions have no relevant chunks by design;
            # they belong to evaluate_answers.py's refusal check, not here.
            continue

        start = time.perf_counter()
        retrieved = fn(item['question'])
        latencies.append(time.perf_counter() - start)

        for k in K_VALUES:
            per_question[f'recall@{k}'].append(metrics.recall_at_k(retrieved, relevant, k))
        per_question['mrr'].append(metrics.reciprocal_rank(retrieved, relevant))
        per_question['ndcg@5'].append(metrics.ndcg_at_k(retrieved, relevant, 5))

    result = {k: metrics.mean(v) for k, v in per_question.items()}
    result['mean_latency_ms'] = round(metrics.mean(latencies) * 1000, 1)
    result['n_questions'] = len(latencies)
    return {name: result}


def render_report(results: dict, golden_set_path: str) -> str:
    configs = ['A. Vector only', 'B. BM25 only', 'C. Hybrid + RRF', 'D. Hybrid + RRF + rerank']
    metric_cols = ['recall@1', 'recall@3', 'recall@5', 'recall@10', 'mrr', 'ndcg@5', 'mean_latency_ms']

    lines = [
        '# Retrieval evaluation report',
        '',
        f'Golden set: `{golden_set_path}` ({next(iter(results.values()))["n_questions"]} scored questions)',
        '',
        '| Config | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR | nDCG@5 | Latency (ms) |',
        '|---|---|---|---|---|---|---|---|',
    ]
    for name in configs:
        r = results[name]
        lines.append(
            f"| {name} | {r['recall@1']} | {r['recall@3']} | {r['recall@5']} | "
            f"{r['recall@10']} | {r['mrr']} | {r['ndcg@5']} | {r['mean_latency_ms']} |"
        )

    a, d = results['A. Vector only'], results['D. Hybrid + RRF + rerank']
    delta = round(d['recall@5'] - a['recall@5'], 4)
    lines += [
        '',
        f"**A -> D change in Recall@5: {delta:+.4f}** "
        f"({a['recall@5']} -> {d['recall@5']}).",
        '',
        'D adds latency (fusion over two retrieval methods plus a cross-encoder '
        'pass) in exchange for retrieval quality — that tradeoff, not just the '
        'headline recall number, is what to lead with when asked about it.',
    ]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--golden-set', default=os.path.join(
        os.path.dirname(__file__), 'golden_set.json'))
    args = parser.parse_args()

    golden_set = load_golden_set(args.golden_set)
    vector_store = VectorStore()

    results = {}
    results.update(evaluate_config('A. Vector only', lambda q: config_a_vector_only(q, vector_store), golden_set))
    results.update(evaluate_config('B. BM25 only', config_b_bm25_only, golden_set))
    results.update(evaluate_config('C. Hybrid + RRF', lambda q: config_c_hybrid_rrf(q, vector_store), golden_set))
    results.update(evaluate_config('D. Hybrid + RRF + rerank', lambda q: config_d_hybrid_rrf_rerank(q, vector_store), golden_set))

    report = render_report(results, args.golden_set)

    results_dir = os.path.join(os.path.dirname(__file__), 'results')
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, 'report.md'), 'w', encoding='utf-8') as f:
        f.write(report)
    with open(os.path.join(results_dir, 'retrieval_raw.json'), 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    print(report)
    print(f"Saved to {results_dir}/report.md")


if __name__ == '__main__':
    main()
