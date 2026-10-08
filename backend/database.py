import sqlite3
import os
from contextlib import contextmanager
from config import Config


def get_connection():
    os.makedirs(os.path.dirname(Config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    # FIX: SQLite disables foreign keys by default, which meant every
    # ON DELETE CASCADE in the schema below was silently doing nothing.
    # Deleting a document left orphaned tags, action items, decisions and ideas.
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


@contextmanager
def db_cursor(commit=False):
    """Connection that always closes, and rolls back if anything raises.

    FIX: previously every route opened a connection manually and only closed it
    on the happy path — early returns (404s) and exceptions leaked connections.
    """
    conn = get_connection()
    try:
        yield conn
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db_cursor(commit=True) as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                filename TEXT,
                stored_filename TEXT,
                file_type TEXT,
                content TEXT,
                summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                word_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                is_processed BOOLEAN DEFAULT FALSE
            );

            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                color TEXT DEFAULT '#6366f1',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS document_tags (
                document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
                tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (document_id, tag_id)
            );

            CREATE TABLE IF NOT EXISTS action_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                is_done BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS key_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS key_ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                response TEXT NOT NULL,
                sources TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- FIX: keyword search used LIKE '%query%', which cannot use an index
            -- and scans every document's full text. FTS5 gives real inverted-index
            -- search. Triggers keep it in sync with the documents table.
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                title,
                content,
                content='documents',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, title, content)
                VALUES (new.id, new.title, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, title, content)
                VALUES ('delete', old.id, old.title, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, title, content)
                VALUES ('delete', old.id, old.title, old.content);
                INSERT INTO documents_fts(rowid, title, content)
                VALUES (new.id, new.title, new.content);
            END;

            -- UPGRADE (Phase 2.2): chunk-level FTS5 index for hybrid retrieval.
            -- documents_fts above matches whole documents (kept for /search
            -- backward-compat with the old response shape). This one indexes
            -- individual chunks so BM25 results can be fused with the
            -- chunk-level semantic results from ChromaDB — same granularity,
            -- which is what makes RRF fusion between them meaningful.
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                chunk_id UNINDEXED,
                doc_id UNINDEXED,
                title,
                content,
                tokenize = 'porter unicode61'
            );

            CREATE INDEX IF NOT EXISTS idx_documents_created
                ON documents(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_action_items_doc
                ON action_items(document_id);

            -- UPGRADE (Phase 1.1): audit trail for background ingestion jobs.
            -- Live status during a job is served from the in-memory registry
            -- in core/jobs.py (faster for polling); this table is the durable
            -- record so job history survives a server restart.
            CREATE TABLE IF NOT EXISTS ingest_jobs (
                id TEXT PRIMARY KEY,
                document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'queued',
                stage TEXT,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
        ''')

    print("Database initialized successfully")


if __name__ == "__main__":
    init_db()
