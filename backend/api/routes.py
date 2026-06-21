import os
import json
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime
from database import get_connection
from core.ingestor import DocumentIngestor
from core.embedder import VectorStore
from core.summarizer import Summarizer
from config import Config

api = Blueprint('api', __name__)

ingestor = DocumentIngestor()
vector_store = VectorStore()
summarizer = Summarizer()

ALLOWED_EXTENSIONS = {'pdf', 'txt', 'md', 'markdown', 'json'}
UPLOAD_FOLDER = 'data/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ─────────────────────────────────────────
# DOCUMENTS
# ─────────────────────────────────────────

@api.route('/documents', methods=['GET'])
def get_documents():
    conn = get_connection()
    docs = conn.execute('''
        SELECT d.*, GROUP_CONCAT(t.name) as tags
        FROM documents d
        LEFT JOIN document_tags dt ON d.id = dt.document_id
        LEFT JOIN tags t ON dt.tag_id = t.id
        GROUP BY d.id
        ORDER BY d.created_at DESC
    ''').fetchall()
    conn.close()
    return jsonify([dict(d) for d in docs])

@api.route('/documents/<int:doc_id>', methods=['GET'])
def get_document(doc_id):
    conn = get_connection()
    doc = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
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

    conn.close()
    return jsonify({
        **dict(doc),
        'tags': [dict(t) for t in tags],
        'action_items': [dict(a) for a in action_items],
        'key_decisions': [dict(k) for k in key_decisions],
        'key_ideas': [dict(k) for k in key_ideas]
    })

@api.route('/documents/upload', methods=['POST'])
def upload_document():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    title = request.form.get('title', file.filename)

    if not allowed_file(file.filename):
        return jsonify({'error': f'File type not allowed. Supported: {ALLOWED_EXTENSIONS}'}), 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)

    try:
        file_type = ingestor.get_file_type(filename)
        text = ingestor.extract_text(file_path, file_type)
        chunks = ingestor.chunk_text(text)
        word_count = ingestor.get_word_count(text)

        conn = get_connection()
        cursor = conn.execute('''
            INSERT INTO documents (title, filename, file_type, content, word_count, chunk_count)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, filename, file_type, text, word_count, len(chunks)))
        doc_id = cursor.lastrowid
        conn.commit()

        # Embed chunks
        vector_store.add_chunks(doc_id, chunks, title)

        # AI processing
        print(f"🤖 Processing document with AI...")
        summary = summarizer.summarize(text)
        tags = summarizer.extract_tags(text)
        action_items = summarizer.extract_action_items(text)
        key_decisions = summarizer.extract_key_decisions(text)
        key_ideas = summarizer.extract_key_ideas(text)

        # Save summary
        conn.execute('''
            UPDATE documents SET summary = ?, is_processed = TRUE
            WHERE id = ?
        ''', (summary, doc_id))

        # Save tags
        for tag_name in tags:
            conn.execute('INSERT OR IGNORE INTO tags (name) VALUES (?)', (tag_name,))
            tag = conn.execute('SELECT id FROM tags WHERE name = ?', (tag_name,)).fetchone()
            if tag:
                conn.execute(
                    'INSERT OR IGNORE INTO document_tags VALUES (?, ?)',
                    (doc_id, tag['id'])
                )

        # Save action items
        for item in action_items:
            conn.execute(
                'INSERT INTO action_items (document_id, content) VALUES (?, ?)',
                (doc_id, item)
            )

        # Save key decisions
        for decision in key_decisions:
            conn.execute(
                'INSERT INTO key_decisions (document_id, content) VALUES (?, ?)',
                (doc_id, decision)
            )

        # Save key ideas
        for idea in key_ideas:
            conn.execute(
                'INSERT INTO key_ideas (document_id, content) VALUES (?, ?)',
                (doc_id, idea)
            )

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'doc_id': doc_id,
            'title': title,
            'word_count': word_count,
            'chunk_count': len(chunks),
            'summary': summary,
            'tags': tags,
            'action_items': action_items,
            'key_decisions': key_decisions,
            'key_ideas': key_ideas
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api.route('/documents/<int:doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    conn = get_connection()
    doc = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
    if not doc:
        return jsonify({'error': 'Document not found'}), 404

    vector_store.delete_document(doc_id)
    conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Document {doc_id} deleted'})

# ─────────────────────────────────────────
# SEARCH & QUERY
# ─────────────────────────────────────────

@api.route('/search', methods=['POST'])
def search():
    data = request.json
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': 'Query is required'}), 400

    # Semantic search
    semantic_results = vector_store.search(query)

    # Keyword search
    conn = get_connection()
    keyword_results = conn.execute('''
        SELECT id, title, summary, created_at
        FROM documents
        WHERE content LIKE ? OR title LIKE ?
        LIMIT 5
    ''', (f'%{query}%', f'%{query}%')).fetchall()
    conn.close()

    return jsonify({
        'query': query,
        'semantic_results': semantic_results,
        'keyword_results': [dict(r) for r in keyword_results]
    })

@api.route('/query', methods=['POST'])
def query():
    data = request.json
    question = data.get('question', '').strip()
    if not question:
        return jsonify({'error': 'Question is required'}), 400

    # Get relevant chunks
    chunks = vector_store.search(question)

    # Generate answer
    answer = summarizer.answer_query(question, chunks)

    # Save to chat history
    sources = list(set([c['title'] for c in chunks]))
    conn = get_connection()
    conn.execute('''
        INSERT INTO chat_history (query, response, sources)
        VALUES (?, ?, ?)
    ''', (question, answer, json.dumps(sources)))
    conn.commit()
    conn.close()

    return jsonify({
        'question': question,
        'answer': answer,
        'sources': sources,
        'context_used': len(chunks)
    })

# ─────────────────────────────────────────
# TAGS
# ─────────────────────────────────────────

@api.route('/tags', methods=['GET'])
def get_tags():
    conn = get_connection()
    tags = conn.execute('''
        SELECT t.*, COUNT(dt.document_id) as doc_count
        FROM tags t
        LEFT JOIN document_tags dt ON t.id = dt.tag_id
        GROUP BY t.id
        ORDER BY doc_count DESC
    ''').fetchall()
    conn.close()
    return jsonify([dict(t) for t in tags])

# ─────────────────────────────────────────
# CHAT HISTORY
# ─────────────────────────────────────────

@api.route('/history', methods=['GET'])
def get_history():
    conn = get_connection()
    history = conn.execute(
        'SELECT * FROM chat_history ORDER BY created_at DESC LIMIT 50'
    ).fetchall()
    conn.close()
    return jsonify([dict(h) for h in history])

# ─────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────

@api.route('/analytics', methods=['GET'])
def get_analytics():
    conn = get_connection()

    total_docs = conn.execute('SELECT COUNT(*) as c FROM documents').fetchone()['c']
    total_chunks = vector_store.get_total_chunks()
    total_queries = conn.execute('SELECT COUNT(*) as c FROM chat_history').fetchone()['c']
    total_words = conn.execute(
        'SELECT SUM(word_count) as s FROM documents'
    ).fetchone()['s'] or 0
    total_tags = conn.execute('SELECT COUNT(*) as c FROM tags').fetchone()['c']
    total_actions = conn.execute(
        'SELECT COUNT(*) as c FROM action_items WHERE is_done = FALSE'
    ).fetchone()['c']

    recent_docs = conn.execute('''
        SELECT title, created_at, word_count FROM documents
        ORDER BY created_at DESC LIMIT 5
    ''').fetchall()

    conn.close()
    return jsonify({
        'total_documents': total_docs,
        'total_chunks': total_chunks,
        'total_queries': total_queries,
        'total_words': total_words,
        'total_tags': total_tags,
        'pending_actions': total_actions,
        'recent_documents': [dict(d) for d in recent_docs]
    })
