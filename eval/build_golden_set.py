"""Draft a golden set from your actual uploaded documents.

UPGRADE_PLAN.md Phase 3.1 calls for 40-60 hand-written Q&A pairs with known
relevant_chunk_ids. That's only possible against real content — this repo
has none of your documents in it, so this script can't be run here. It's
meant to be run on your machine, against your own MindVault database, once
you've uploaded a handful of real notes/documents.

What it does:
  1. Reads every chunk out of chunks_fts (the real chunk_ids your app will
     actually retrieve against).
  2. Samples a spread of chunks and asks your local LLM to draft one
     factual question per chunk, with the answer contained in that chunk.
  3. Writes eval/golden_set.draft.json for you to review by hand.

What it deliberately does NOT do: auto-generate 'multi-hop', 'negative',
or 'paraphrase' questions. Those need a human who knows the corpus —
- multi-hop: a question whose answer spans two chunks you pick yourself
- negative: a question about something genuinely absent from your docs
- paraphrase: reword an existing factual question differently
The plan is explicit that hand-writing these is "genuinely boring work"
but is what makes the eval set trustworthy — an LLM drafting its own exam
questions and grading itself on them proves nothing.

Usage:
    cd backend && python ../eval/build_golden_set.py --sample 20

Review eval/golden_set.draft.json, edit/delete entries, add multi-hop and
negative cases by hand, then rename it to eval/golden_set.json.
"""

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from database import get_connection  # noqa: E402
from langchain_ollama import OllamaLLM  # noqa: E402
from config import Config  # noqa: E402


DRAFT_PROMPT = """You are drafting an evaluation question for a RAG system.
Given the following text chunk, write ONE factual question that this chunk
directly and completely answers. Then list 2-4 short keywords/phrases that
a correct answer must contain.

Respond in exactly this format, nothing else:
QUESTION: <question>
KEYWORDS: <comma-separated keywords>

Chunk:
{chunk}
"""


def fetch_chunks():
    conn = get_connection()
    try:
        rows = conn.execute(
            'SELECT chunk_id, doc_id, title, content FROM chunks_fts'
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def draft_question(llm, chunk_text: str) -> dict | None:
    response = llm.invoke(DRAFT_PROMPT.format(chunk=chunk_text[:1500])).strip()
    question, keywords = None, []
    for line in response.split('\n'):
        if line.upper().startswith('QUESTION:'):
            question = line.split(':', 1)[1].strip()
        elif line.upper().startswith('KEYWORDS:'):
            keywords = [k.strip() for k in line.split(':', 1)[1].split(',') if k.strip()]
    if not question:
        return None
    return {'question': question, 'keywords': keywords}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sample', type=int, default=20,
                         help='how many chunks to draft questions from')
    args = parser.parse_args()

    chunks = fetch_chunks()
    if not chunks:
        print("No chunks found in chunks_fts. Upload some documents first, "
              "then run this again.")
        return

    sample = random.sample(chunks, min(args.sample, len(chunks)))
    llm = OllamaLLM(model=Config.LLM_MODEL, base_url=Config.OLLAMA_BASE_URL, temperature=0.2)

    entries = []
    for i, chunk in enumerate(sample, start=1):
        drafted = draft_question(llm, chunk['content'])
        if not drafted:
            continue
        entries.append({
            'id': f'q{i:03d}',
            'question': drafted['question'],
            'relevant_chunk_ids': [chunk['chunk_id']],
            'expected_answer_contains': drafted['keywords'],
            'category': 'factual',
            '_source_doc': chunk['title'],
        })
        print(f"[{i}/{len(sample)}] {drafted['question']}")

    out_path = os.path.join(os.path.dirname(__file__), 'golden_set.draft.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(entries)} draft questions to {out_path}")
    print("Review each one by hand, then add your own multi-hop, negative, "
          "and paraphrase cases (see docstring at the top of this file) "
          "before renaming it to golden_set.json.")


if __name__ == '__main__':
    main()
