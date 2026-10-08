import os
import json
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, request, jsonify, Response, stream_with_context
from werkzeug.utils import secure_filename
from database import get_connection, db_cursor
from core.ingestor import DocumentIngestor
from core.embedder import VectorStore
from core.summarizer import Summarizer
from core import jobs
from core import retriever
from config import Config

logger = logging.getLogger(__name__)

api = Blueprint('api', __name__)

ingestor = DocumentIngestor()
vector_store = VectorStore()
summarizer = Summarizer()

ALLOWED_EXTENSIONS = {'pdf', 'txt', 'md', 'markdown', 'json'}
UPLOAD_FOLDER = 'data/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

_extract_pool = ThreadPoolExecutor(max_workers=5)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def build_stored_filename(original_name):
    safe = secure_filename(original_name) or 'upload'
    return f"{uuid.uuid4().hex}_{safe}"


# ─────────────────────────────────────────
# DOCUMENTS
# ─────────────────────────────────────────

@api.route('/documents', methods=['GET'])
def get_documents():
    with db_cursor() as conn:
        docs = conn.execute('''
            SELECT d.*, GROUP_CONCAT(t.name) as tags
            FROM documents d
            LEFT JOIN document_tags dt ON d.id = dt.document_id
            LEFT JOIN tags t ON dt.tag_id = t.id
            GROUP BY d.id
            ORDER BY d.created_at DESC
        ''').fetchall()
    return jsonify([dict(d) for d in docs])


@api.route('/documents/<int:doc_id>', methods=['GET'])
def get_document(doc_id):
    with db_cursor() as conn:
        doc = conn.execute(
            'SELECT * FROM documents WHERE id = ?', (doc_id,)
        ).fetchone()
        if not doc:
            return jsonify({'error': 'Document not found'}), 404

        tags = conn.execute('''
            SELECT t.* FROM tags t
            JOIN document_tags dt ON t.id = dt.tag_id
            WHERE dt.document_id = ?
        ''', (doc_id,)).fetchall()

        action_items = conn.execute(
            'SELECT * FROM action_items WHERE document_id = ?', (doc_id,)
        ).fetchall()

        key_decisions = conn.execute(
            'SELECT * FROM key_decisions WHERE document_id = ?', (doc_id,)
        ).fetchall()

        key_ideas = conn.execute(
            'SELECT * FROM key_ideas WHERE document_id = ?', (doc_id,)
        ).fetchall()

    return jsonify({
        **dict(doc),
        'tags': [dict(t) for t in tags],
        'action_items': [dict(a) for a in action_items],
        'key_decisions': [dict(k) for k in key_decisions],
        'key_ideas': [dict(k) for k in key_ideas]
    })


def _process_document_background(doc_id: int, text: str, chunks: list, title: str, job_id: str):
    """Runs off the request thread: embed + 5 LLM extractions + persist.

    UPGRADE (Phase 1.2/1.3): this used to run inline inside the upload
    request. Now it's submitted to core.jobs and runs here instead. The
    five extraction calls are independent (same input, different output
    tables) so they run concurrently via ThreadPoolExecutor rather than
    one after another — cuts wall-clock time roughly 3-4x on a machine
    that isn't already saturated. If your hardware is the bottleneck
    instead of round-trip latency, this won't help much; that's worth
    benchmarking rather than assuming.
    """
    jobs.update_job(job_id, stage='embedding', progress=10)
    vector_store.add_chunks(doc_id, chunks, title)

    # UPGRADE (Phase 2.2): keep chunks_fts in sync at the same granularity
    # as the vectors just added, so retriever.py's BM25 side and vector
    # side are searching the same units and RRF fusion lines up 1:1.
    with db_cursor(commit=True) as fts_conn:
        for i, chunk in enumerate(chunks):
            fts_conn.execute(
                'INSERT INTO chunks_fts (chunk_id, doc_id, title, content) VALUES (?, ?, ?, ?)',
                (f'doc_{doc_id}_chunk_{i}', doc_id, title, chunk)
            )

    jobs.update_job(job_id, stage='summarizing', progress=30)

    futures = {
        'summary': _extract_pool.submit(summarizer.summarize, text),
        'tags': _extract_pool.submit(summarizer.extract_tags, text),
        'action_items': _extract_pool.submit(summarizer.extract_action_items, text),
        'key_decisions': _extract_pool.submit(summarizer.extract_key_decisions, text),
        'key_ideas': _extract_pool.submit(summarizer.extract_key_ideas, text),
    }
    results = {name: f.result() for name, f in futures.items()}

    jobs.update_job(job_id, stage='saving', progress=90)

    conn = get_connection()
    try:
        conn.execute(
            'UPDATE documents SET summary = ?, is_processed = TRUE WHERE id = ?',
            (results['summary'], doc_id)
        )

        for tag_name in results['tags']:
            conn.execute('INSERT OR IGNORE INTO tags (name) VALUES (?)', (tag_name,))
            tag = conn.execute('SELECT id FROM tags WHERE name = ?', (tag_name,)).fetchone()
            if tag:
                conn.execute(
                    'INSERT OR IGNORE INTO document_tags (document_id, tag_id) VALUES (?, ?)',
                    (doc_id, tag['id'])
                )

        for item in results['action_items']:
            conn.execute(
                'INSERT INTO action_items (document_id, content) VALUES (?, ?)',
                (doc_id, item)
            )
        for decision in results['key_decisions']:
            conn.execute(
                'INSERT INTO key_decisions (document_id, content) VALUES (?, ?)',
                (doc_id, decision)
            )
        for idea in results['key_ideas']:
            conn.execute(
                'INSERT INTO key_ideas (document_id, content) VALUES (?, ?)',
                (doc_id, idea)
            )

        conn.execute(
            "UPDATE ingest_jobs SET status='complete', stage='complete', completed_at=CURRENT_TIMESTAMP WHERE id=?",
            (job_id,)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@api.route('/documents/upload', methods=['POST'])
def upload_document():
    """Validate, save, extract and chunk synchronously (fast, no LLM calls);
    then hand off embedding + summarization to a background job.

    UPGRADE (Phase 1.2): previously this endpoint didn't return until
    embedding AND five sequential LLM calls finished — 60-120s of a frozen
    request on llama3.1:8b. Now it returns as soon as the document exists
    and is chunked, with a job_id the client polls or subscribes to via SSE.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({
            'error': f'File type not allowed. Supported: {sorted(ALLOWED_EXTENSIONS)}'
        }), 400

    title = request.form.get('title') or file.filename
    original_name = file.filename
    stored_name = build_stored_filename(original_name)
    file_path = os.path.join(UPLOAD_FOLDER, stored_name)
    file.save(file_path)

    conn = get_connection()
    try:
        file_type = ingestor.get_file_type(original_name)
        text = ingestor.extract_text(file_path, file_type)
        chunks = ingestor.chunk_text(text)
        word_count = ingestor.get_word_count(text)

        cursor = conn.execute('''
            INSERT INTO documents
                (title, filename, stored_filename, file_type, content, word_count, chunk_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, original_name, stored_name, file_type, text, word_count, len(chunks)))
        doc_id = cursor.lastrowid

        job_id = jobs.create_job(doc_id)
        conn.execute(
            'INSERT INTO ingest_jobs (id, document_id, status, stage) VALUES (?, ?, ?, ?)',
            (job_id, doc_id, 'queued', 'queued')
        )
        conn.commit()

    except Exception:
        conn.rollback()
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass
        logger.exception('Upload failed during extraction for %s', original_name)
        return jsonify({'error': 'Failed to process document'}), 500
    finally:
        conn.close()

    jobs.submit(job_id, _process_document_background, doc_id, text, chunks, title, job_id)

    return jsonify({
        'success': True,
        'doc_id': doc_id,
        'job_id': job_id,
        'title': title,
        'word_count': word_count,
        'chunk_count': len(chunks),
    }), 202


@api.route('/documents/<int:doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    with db_cursor(commit=True) as conn:
        doc = conn.execute(
            'SELECT * FROM documents WHERE id = ?', (doc_id,)
        ).fetchone()
        if not doc:
            return jsonify({'error': 'Document not found'}), 404

        stored_name = doc['stored_filename'] or doc['filename']
        vector_store.delete_document(doc_id)
        # chunks_fts isn't linked by a real foreign key (FTS5 virtual
        # tables can't declare one), so ON DELETE CASCADE won't touch it —
        # clean it up explicitly or deleted docs keep showing up in
        # keyword/hybrid search results.
        conn.execute('DELETE FROM chunks_fts WHERE doc_id = ?', (doc_id,))
        conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))

    if stored_name:
        file_path = os.path.join(UPLOAD_FOLDER, stored_name)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            logger.exception('Could not delete file for doc_id=%s', doc_id)

    return jsonify({'success': True, 'message': f'Document {doc_id} deleted'})


# ─────────────────────────────────────────
# JOB STATUS  (Phase 1.4)
# ─────────────────────────────────────────

@api.route('/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Polling fallback for clients that don't use SSE."""
    job = jobs.get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)


@api.route('/jobs/<job_id>/stream')
def stream_job_status(job_id):
    """Server-Sent Events progress stream for one ingestion job.

    UPGRADE (Phase 1.4): SSE rather than WebSockets — this is one-directional
    server-to-client progress, which is exactly what SSE is for, and it works
    over plain HTTP with no extra dependency or handshake.
    """
    import time

    def generate():
        last_stage = None
        for _ in range(600):  # ~5 min cap
            job = jobs.get_job(job_id)
            if not job:
                yield f"event: error\ndata: {json.dumps({'error': 'job not found'})}\n\n"
                return

            if job['stage'] != last_stage or job['status'] in ('complete', 'error'):
                yield f"data: {json.dumps(job)}\n\n"
                last_stage = job['stage']

            if job['status'] in ('complete', 'error'):
                return

            time.sleep(0.5)

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


# ─────────────────────────────────────────
# SEARCH & QUERY
# ─────────────────────────────────────────

@api.route('/search', methods=['POST'])
def search():
    """Hybrid search: semantic + BM25 full-text, fused with RRF, reranked.

    UPGRADE (Phase 2): retrieval logic now lives in core/retriever.py, the
    file the README already advertised. This route just calls it.
    """
    data = request.get_json(silent=True) or {}
    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({'error': 'Query is required'}), 400

    result = retriever.hybrid_search(query, vector_store)
    return jsonify({'query': query, **result})


@api.route('/query', methods=['POST'])
def query():
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    if not question:
        return jsonify({'error': 'Question is required'}), 400

    chunks = retriever.retrieve_for_answer(question, vector_store)

    if not chunks:
        return jsonify({
            'question': question,
            'answer': "I couldn't find anything relevant in your documents to answer that.",
            'sources': [],
            'context_used': 0
        })

    answer = summarizer.answer_query(question, chunks)
    sources = sorted({c['title'] for c in chunks})

    with db_cursor(commit=True) as conn:
        conn.execute(
            'INSERT INTO chat_history (query, response, sources) VALUES (?, ?, ?)',
            (question, answer, json.dumps(sources))
        )

    return jsonify({
        'question': question,
        'answer': answer,
        'sources': sources,
        'context_used': len(chunks)
    })


@api.route('/query/stream', methods=['POST'])
def query_stream():
    """Streaming answer endpoint (Phase 1.5).

    Emits sources first (retrieval finishes before generation starts),
    then streams answer tokens as Ollama produces them, then persists
    the completed answer to chat_history.
    """
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    if not question:
        return jsonify({'error': 'Question is required'}), 400

    chunks = retriever.retrieve_for_answer(question, vector_store)
    sources = sorted({c['title'] for c in chunks}) if chunks else []

    def generate():
        yield f"event: sources\ndata: {json.dumps({'sources': sources, 'context_used': len(chunks)})}\n\n"

        full_answer = []
        for token in summarizer.stream_answer(question, chunks):
            full_answer.append(token)
            yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"

        answer = ''.join(full_answer)
        with db_cursor(commit=True) as conn:
            conn.execute(
                'INSERT INTO chat_history (query, response, sources) VALUES (?, ?, ?)',
                (question, answer, json.dumps(sources))
            )

        yield f"event: done\ndata: {json.dumps({'answer': answer})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


# ─────────────────────────────────────────
# TAGS
# ─────────────────────────────────────────

@api.route('/tags', methods=['GET'])
def get_tags():
    with db_cursor() as conn:
        tags = conn.execute('''
            SELECT t.*, COUNT(dt.document_id) as doc_count
            FROM tags t
            LEFT JOIN document_tags dt ON t.id = dt.tag_id
            GROUP BY t.id
            ORDER BY doc_count DESC
        ''').fetchall()
    return jsonify([dict(t) for t in tags])


# ─────────────────────────────────────────
# CHAT HISTORY
# ─────────────────────────────────────────

@api.route('/history', methods=['GET'])
def get_history():
    with db_cursor() as conn:
        history = conn.execute(
            'SELECT * FROM chat_history ORDER BY created_at DESC LIMIT 50'
        ).fetchall()
    return jsonify([dict(h) for h in history])


# ─────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────

@api.route('/analytics', methods=['GET'])
def get_analytics():
    with db_cursor() as conn:
        stats = conn.execute('''
            SELECT
                (SELECT COUNT(*) FROM documents) AS total_docs,
                (SELECT COUNT(*) FROM chat_history) AS total_queries,
                (SELECT COALESCE(SUM(word_count), 0) FROM documents) AS total_words,
                (SELECT COUNT(*) FROM tags) AS total_tags,
                (SELECT COUNT(*) FROM action_items WHERE is_done = FALSE) AS pending_actions
        ''').fetchone()

        recent_docs = conn.execute('''
            SELECT title, created_at, word_count FROM documents
            ORDER BY created_at DESC LIMIT 5
        ''').fetchall()

    return jsonify({
        'total_documents': stats['total_docs'],
        'total_chunks': vector_store.get_total_chunks(),
        'total_queries': stats['total_queries'],
        'total_words': stats['total_words'],
        'total_tags': stats['total_tags'],
        'pending_actions': stats['pending_actions'],
        'recent_documents': [dict(d) for d in recent_docs]
    })
