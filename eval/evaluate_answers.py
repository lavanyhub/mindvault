"""Phase 3.3 — answer quality: groundedness, refusal accuracy, citation.

Runs the full retrieve-then-answer pipeline (retriever.retrieve_for_answer
+ summarizer.answer_query) for every golden question, then uses the local
LLM as a judge to score three things:

  groundedness   — is every claim in the answer traceable to the retrieved
                    context, rather than the model's own knowledge?
  refusal        — for 'negative' category questions, did it correctly say
                    it doesn't know, instead of confabulating an answer?
  keyword_hit    — does the answer contain the expected_answer_contains
                    terms from the golden set (a cheap non-LLM sanity check
                    run alongside the judge, not a replacement for it)?

LLM-as-judge is still local Ollama, so this stays zero-cost, but it's not
free of bias — the same model family grading its own generations tends to
be lenient. Treat these numbers as directional, and spot-check a sample by
hand before quoting them anywhere.

Usage:
    cd backend && python ../eval/evaluate_answers.py
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from core.embedder import VectorStore  # noqa: E402
from core.summarizer import Summarizer  # noqa: E402
from core import retriever  # noqa: E402
from langchain_ollama import OllamaLLM  # noqa: E402
from config import Config  # noqa: E402


JUDGE_PROMPT = """You are grading a RAG system's answer for groundedness.
An answer is GROUNDED if every factual claim in it is supported by the
provided context. It is NOT grounded if it states anything the context
doesn't say, even if the claim happens to be true in general.

Context:
{context}

Question: {question}

Answer to grade: {answer}

Respond in exactly this format, nothing else:
GROUNDED: yes or no
REASON: <one sentence>
"""

REFUSAL_PHRASES = [
    "don't have information",
    "do not have information",
    "couldn't find",
    "could not find",
    "no information about this",
    "not in your knowledge base",
]


def judge_groundedness(llm, question: str, answer: str, context_chunks: list[dict]) -> dict:
    context = "\n\n---\n\n".join(c['content'] for c in context_chunks[:5]) or "(no context retrieved)"
    response = llm.invoke(JUDGE_PROMPT.format(
        context=context, question=question, answer=answer
    )).strip()

    grounded, reason = None, ''
    for line in response.split('\n'):
        if line.upper().startswith('GROUNDED:'):
            grounded = 'yes' in line.lower()
        elif line.upper().startswith('REASON:'):
            reason = line.split(':', 1)[1].strip()
    return {'grounded': grounded, 'reason': reason}


def looks_like_refusal(answer: str) -> bool:
    lowered = answer.lower()
    return any(phrase in lowered for phrase in REFUSAL_PHRASES)


def keyword_hit(answer: str, expected: list[str]) -> float:
    if not expected:
        return None
    lowered = answer.lower()
    hits = sum(1 for kw in expected if kw.lower() in lowered)
    return round(hits / len(expected), 3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--golden-set', default=os.path.join(
        os.path.dirname(__file__), 'golden_set.json'))
    args = parser.parse_args()

    if not os.path.exists(args.golden_set):
        example = os.path.join(os.path.dirname(__file__), 'golden_set.example.json')
        print(f"{args.golden_set} not found. Run build_golden_set.py first, "
              f"or see the schema in {example}.")
        return

    with open(args.golden_set, encoding='utf-8') as f:
        golden_set = json.load(f)

    vector_store = VectorStore()
    summarizer = Summarizer()
    judge = OllamaLLM(model=Config.LLM_MODEL, base_url=Config.OLLAMA_BASE_URL, temperature=0.0)

    rows = []
    for item in golden_set:
        question = item['question']
        is_negative = item.get('category') == 'negative'

        chunks = retriever.retrieve_for_answer(question, vector_store)
        answer = summarizer.answer_query(question, chunks)

        row = {
            'id': item.get('id'),
            'category': item.get('category', 'factual'),
            'question': question,
            'answer': answer,
            'keyword_hit': keyword_hit(answer, item.get('expected_answer_contains', [])),
        }

        if is_negative:
            row['correctly_refused'] = looks_like_refusal(answer)
        else:
            judged = judge_groundedness(judge, question, answer, chunks)
            row['grounded'] = judged['grounded']
            row['grounded_reason'] = judged['reason']

        rows.append(row)
        print(f"[{row['id']}] {row.get('grounded', row.get('correctly_refused'))}  {question[:60]}")

    negatives = [r for r in rows if r['category'] == 'negative']
    positives = [r for r in rows if r['category'] != 'negative']

    refusal_accuracy = (
        round(sum(1 for r in negatives if r['correctly_refused']) / len(negatives), 3)
        if negatives else None
    )
    groundedness_rate = (
        round(sum(1 for r in positives if r['grounded']) / len(positives), 3)
        if positives else None
    )
    keyword_scores = [r['keyword_hit'] for r in rows if r['keyword_hit'] is not None]
    mean_keyword_hit = round(sum(keyword_scores) / len(keyword_scores), 3) if keyword_scores else None

    summary = {
        'n_questions': len(rows),
        'n_negative': len(negatives),
        'n_positive': len(positives),
        'groundedness_rate': groundedness_rate,
        'refusal_accuracy': refusal_accuracy,
        'mean_keyword_hit': mean_keyword_hit,
    }

    results_dir = os.path.join(os.path.dirname(__file__), 'results')
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, 'answer_quality.json'), 'w', encoding='utf-8') as f:
        json.dump({'summary': summary, 'rows': rows}, f, indent=2, ensure_ascii=False)

    report_lines = [
        '# Answer quality report',
        '',
        f"- Questions evaluated: {summary['n_questions']} "
        f"({summary['n_positive']} factual/multi-hop/paraphrase, {summary['n_negative']} negative)",
        f"- Groundedness rate: {summary['groundedness_rate']}",
        f"- Refusal accuracy (negatives): {summary['refusal_accuracy']}",
        f"- Mean expected-keyword hit rate: {summary['mean_keyword_hit']}",
        '',
        'Groundedness and refusal accuracy are graded by the local LLM judging '
        'its own model family\'s output — treat as directional, spot-check a '
        'sample of `results/answer_quality.json` by hand before citing these '
        'numbers anywhere.',
    ]
    with open(os.path.join(results_dir, 'answer_quality.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines) + '\n')

    print('\n' + '\n'.join(report_lines))


if __name__ == '__main__':
    main()
