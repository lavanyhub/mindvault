"""Temp inspection script - safe to delete."""
import os, sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

db = os.path.join(os.path.dirname(__file__), '..', 'data', 'mindvault.db')
conn = sqlite3.connect(db)

print("=== documents ===")
for r in conn.execute(
    "SELECT id, title, file_type, word_count, chunk_count, is_processed FROM documents"
):
    print("  ", r)

for t in ['documents', 'chunks_fts', 'chat_history', 'action_items', 'key_ideas', 'tags']:
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"count {t}: {n}")
    except Exception as e:
        print(f"count {t}: ERR {e}")

print("\n=== sample chunk ids ===")
try:
    for r in conn.execute("SELECT chunk_id, doc_id, substr(title,1,40) FROM chunks_fts LIMIT 8"):
        print("  ", r)
except Exception as e:
    print("  ERR", e)
conn.close()
