# MindVault Upgrade Plan

Turning a working RAG demo into a defensible, real-time system.

---

## Current state (audit)

**What's genuinely good:**
- Clean separation: `ingestor` → `embedder` → `summarizer`, wired through a Flask blueprint
- Real vector pipeline: ChromaDB with cosine space, persistent client, proper chunk IDs (`doc_{id}_chunk_{i}`)
- `RecursiveCharacterTextSplitter` with sensible separators and a 50-char minimum chunk filter
- Grounded generation — `answer_query` explicitly instructs the model to refuse when context is missing
- Cascade deletes are correctly declared in the schema
- Local-first on Ollama, zero API cost — a real architectural stance, not a limitation

**What's broken or overclaimed:**

| # | Issue | Location | Severity |
|---|---|---|---|
| 1 | `retriever.py` is empty (one space) but README lists it as "RAG retrieval" | `backend/core/retriever.py` | High — interviewers open this file |
| 2 | Upload blocks on 5 sequential LLM calls + embedding, synchronously | `routes.py:92-171` | High — 60-120s frozen tab |
| 3 | "Hybrid search" returns two unfused lists, never merged into one ranking | `routes.py:190-214` | High — README overclaims |
| 4 | No evaluation of retrieval quality whatsoever | — | High — blocks resume metrics |
| 5 | No streaming; answer appears in one lump after long silence | `routes.py:216-244` | Medium |
| 6 | `MIN_RELEVANCE_SCORE = 0.3` arbitrary and untested | `config.py:23` | Medium |
| 7 | Fixed `top_k=5`, no reranking | `config.py:22` | Medium |
| 8 | Startup message says port 5000, app runs on 8080 | `app.py:28-29` | Low |
| 9 | `SECRET_KEY` default committed; CORS is `origins="*"` | `config.py:26`, `app.py:13` | Low (local-only, but note it) |
| 10 | Bare `except:` swallows all errors | `ingestor` / gmail-style patterns | Low |

**Dependencies already present** (no new heavy installs needed):
`torch`, `transformers`, `scikit-learn`, `numpy`, `sqlite-fts4`

**New dependencies required:** `rank-bm25`, `sentence-transformers`

---

## Phase 1 — Async ingestion + streaming

**Goal:** upload returns in <200ms; user watches live progress; answers stream token-by-token.

### 1.1 Background job queue

New file: `backend/core/jobs.py`

- `ThreadPoolExecutor(max_workers=2)` — deliberately not Celery/Redis. A local-first single-user app should not require a broker. Document this tradeoff; it's a good interview answer.
- In-memory job registry: `{job_id: {status, stage, progress, doc_id, error}}`
- Stages: `queued → extracting → chunking → embedding → summarizing → complete`

New table in `database.py`:

```sql
CREATE TABLE IF NOT EXISTS ingest_jobs (
    id TEXT PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued',
    stage TEXT,
    progress INTEGER DEFAULT 0,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
```

### 1.2 Split the upload route

`POST /api/documents/upload` becomes:
1. Validate + save file
2. Extract text, chunk, insert `documents` row (fast — no LLM)
3. Submit background job, return `{doc_id, job_id}` immediately

Background worker does: embed chunks → 5 LLM extractions → mark processed.

### 1.3 Parallelize the LLM calls

The five extractions (`summarize`, `extract_tags`, `extract_action_items`, `extract_key_decisions`, `extract_key_ideas`) are **independent** — they all read the same truncated text and write to different tables. Currently sequential.

Ollama serves concurrent requests. Running these through a `ThreadPoolExecutor` cuts wall-clock time roughly 3-4x even after accounting for GPU contention.

> Note: `extract_action_items`, `extract_key_decisions`, and `extract_key_ideas` are three near-identical functions differing only in prompt. Collapse into one `_extract_list(text, instruction)` helper. Removes ~40 lines of duplication.

### 1.4 Progress endpoint (SSE)

`GET /api/jobs/<job_id>/stream` — Server-Sent Events, not WebSockets. One-directional server→client is exactly what SSE is for, and it works over plain HTTP with no extra deps.

Fallback: `GET /api/jobs/<job_id>` for polling.

### 1.5 Streaming answers

`POST /api/query/stream` — SSE endpoint using `OllamaLLM.stream()`.

Emit sources first (retrieval finishes before generation starts), then stream tokens, then persist to `chat_history` on completion.

### 1.6 Frontend

- `Upload.js` — progress bar driven by `EventSource`, per-stage labels
- `Query.js` — append tokens as they arrive; render source chips immediately

**Phase 1 result:** upload feels instant, answers start appearing in ~1s instead of ~30s.

---

## Phase 2 — True hybrid retrieval + reranking

**Goal:** make the README's "hybrid search" claim actually true, and measurably better.

### 2.1 Populate `retriever.py`

Move retrieval out of `embedder.py` and `routes.py` into the file the README already advertises. `embedder.py` keeps only embedding + storage concerns. Clean separation, and the repo structure stops lying.

### 2.2 BM25 keyword index

Current keyword search is `content LIKE '%query%'` over whole documents — matches substrings, ignores term frequency, returns documents not chunks. It cannot be fused with chunk-level semantic results.

Replace with **SQLite FTS5** (built into Python's sqlite3, no new dep) over a `chunks` table, or `rank-bm25` in-memory. FTS5 is the better call — it persists, scales past RAM, and "I used SQLite FTS5 with BM25 ranking" is a stronger sentence than "I used a pip package."

New table:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    doc_id UNINDEXED,
    title,
    content,
    tokenize = 'porter unicode61'
);
```

### 2.3 Reciprocal Rank Fusion

```
RRF_score(d) = Σ  1 / (k + rank_i(d))
```

with `k = 60` (the standard constant from the original Cormack et al. paper).

RRF fuses by *rank*, not score — which matters because cosine similarity and BM25 scores are on incomparable scales. Normalizing them would be arbitrary; RRF sidesteps the problem entirely. This is the single most defensible design decision in the whole upgrade — be ready to explain it.

### 2.4 Cross-encoder reranking

Retrieve top-20 from fusion, rerank with `cross-encoder/ms-marco-MiniLM-L-6-v2`, keep top-5.

Bi-encoders (your current embeddings) encode query and document *separately* — fast, but they never let the two texts attend to each other. Cross-encoders encode them *jointly*, which is far more accurate but too slow to run over the whole corpus. Retrieve-then-rerank gets both properties. ~80MB model, CPU-fine, and `torch`/`transformers` are already installed.

### 2.5 Replace the magic threshold

`MIN_RELEVANCE_SCORE = 0.3` is currently a guess applied to raw cosine distance. After reranking, use the cross-encoder score with a threshold **tuned against the Phase 3 eval set** rather than picked by hand.

Also fix: `n_results=min(top_k, self.collection.count() or 1)` queries an empty collection when no docs exist. Guard with an early return.

### 2.6 Query rewriting (optional, high value)

Follow-up questions like "what about the second one?" retrieve garbage because they're embedded literally. A cheap LLM call rewriting the query against recent `chat_history` fixes conversational retrieval. Cheap to add, very visible in a demo.

---

## Phase 3 — Evaluation harness

**This is the phase that gets you interviews.** Everything above is engineering; this is what lets you make *claims*.

### 3.1 Golden dataset

`eval/golden_set.json` — 40-60 question/answer pairs over a fixed document set:

```json
{
  "id": "q001",
  "question": "What retrieval strategy does MindVault use?",
  "relevant_chunk_ids": ["doc_3_chunk_7", "doc_3_chunk_8"],
  "expected_answer_contains": ["hybrid", "RRF", "cross-encoder"],
  "category": "factual"
}
```

Categories: `factual`, `multi-hop`, `negative` (answer genuinely absent — tests refusal), `paraphrase`.

The **negative** cases matter most. A RAG system that hallucinates confidently on unanswerable questions is worse than useless, and almost nobody tests for it. Having these is a differentiator.

### 3.2 Retrieval metrics

`eval/evaluate_retrieval.py` — Recall@k (k=1,3,5,10), MRR, nDCG@5, plus mean latency.

Run against four configurations:

| Config | Description |
|---|---|
| A | Vector only (current baseline) |
| B | BM25 only |
| C | Hybrid + RRF |
| D | Hybrid + RRF + cross-encoder rerank |

The A→D delta is your resume line.

### 3.3 Answer quality

`eval/evaluate_answers.py` — groundedness (is every claim traceable to retrieved context?), refusal accuracy on negatives, citation correctness. LLM-as-judge via local Ollama, so still zero cost.

### 3.4 Report

`eval/results/report.md` with a comparison table + latency-vs-quality tradeoff chart. Screenshot it into the README.

---

## Phase 4 — README correction

Non-negotiable and takes 20 minutes. Currently the README claims hybrid search that doesn't exist and documents a `retriever.py` that's empty. After Phases 1-3 both become true — but the README also needs:

- Architecture diagram showing the retrieval path
- The eval results table with real numbers
- An honest "Limitations" section (single-user, in-memory job registry, no auth)

A Limitations section reads as *more* competent, not less. It signals you know where the edges are.

---

## Sequencing

| Order | Phase | Why here |
|---|---|---|
| 1 | Phase 3.1 — golden set only | Build the ruler before changing what you measure |
| 2 | Phase 1 — async + streaming | Biggest felt improvement; unblocks fast iteration |
| 3 | Phase 2 — hybrid + rerank | The substantive retrieval work |
| 4 | Phase 3.2-3.4 — full eval | Now there's a real A→D delta to measure |
| 5 | Phase 4 — README | Document what's actually true |

Building the golden set *first* is the key move. If you build it after the improvements, you'll unconsciously write questions your new system happens to answer well, and the numbers become meaningless.

---

## Files affected

**New:**
```
backend/core/jobs.py           # background job queue
backend/core/retriever.py      # (currently empty) hybrid retrieval + RRF + rerank
backend/core/reranker.py       # cross-encoder wrapper
backend/api/streams.py         # SSE endpoints
eval/golden_set.json
eval/evaluate_retrieval.py
eval/evaluate_answers.py
eval/results/report.md
```

**Modified:**
```
backend/database.py            # ingest_jobs table, chunks_fts virtual table
backend/api/routes.py          # split upload, delegate retrieval
backend/core/embedder.py       # strip retrieval, keep embed+store
backend/core/summarizer.py     # collapse 3 duplicate extractors, add stream()
backend/config.py              # RRF_K, RERANK_TOP_N, tuned threshold
backend/requirements.txt       # + rank-bm25, sentence-transformers
backend/app.py                 # fix port message
frontend/src/pages/Upload.js   # SSE progress
frontend/src/pages/Query.js    # streaming answers
frontend/src/api.js            # EventSource helpers
README.md                      # accuracy + results
```

---

## Honest scope estimate

Phase 1 is the largest chunk of code. Phase 2 is the most conceptually interesting. Phase 3 is the most tedious — hand-writing 50 golden questions is genuinely boring work, and it's where this plan is most likely to stall. Consider starting with 20 questions rather than 60; a small eval set that exists beats a large one that doesn't.

**One thing that could go wrong:** running 5 parallel LLM calls plus a cross-encoder on the same machine may saturate your GPU/CPU and make things *slower*, not faster. Phase 1.3 should be benchmarked, not assumed. If parallel is slower, keep it sequential but async — the user still gets an instant response either way, which was the actual goal.
