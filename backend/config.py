import os
import secrets
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Ollama settings
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    LLM_MODEL = os.getenv("LLM_MODEL", "llama3.1:8b")
    EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

    # Database
    DB_PATH = os.getenv("DB_PATH", "data/mindvault.db")
    CHROMA_PATH = os.getenv("CHROMA_PATH", "data/chromadb")

    # Ingestion
    CHUNK_SIZE = 512
    CHUNK_OVERLAP = 64
    MAX_FILE_SIZE_MB = 50

    # RAG
    TOP_K_RESULTS = 5
    # UPGRADE (Phase 2.5): this threshold was picked by feel, not measurement.
    # It's applied to raw cosine similarity in embedder.py's vector-only
    # search path. Once eval/evaluate_retrieval.py (Phase 3) exists, tune
    # this against the golden set instead of guessing. Left as-is for now
    # rather than removed, since embedder.search() is still used standalone
    # by anything that wants pure vector results.
    MIN_RELEVANCE_SCORE = 0.3

    # Flask
    DEBUG = os.getenv("DEBUG", "true").lower() == "true"
    PORT = int(os.getenv("PORT", "8080"))

    # FIX: SECRET_KEY fell back to a hardcoded string committed to the repo.
    # Anyone with the source could forge session cookies. Now a random key is
    # generated for local dev, and production refuses to start without one set.
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        if DEBUG:
            SECRET_KEY = secrets.token_hex(32)
        else:
            raise RuntimeError(
                "SECRET_KEY must be set when DEBUG is false. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )

    # FIX: CORS was origins="*" for every environment.
    CORS_ORIGINS = (
        "*" if DEBUG
        else [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    )
