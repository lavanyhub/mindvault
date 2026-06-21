import os
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
    MIN_RELEVANCE_SCORE = 0.3

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "mindvault-dev-key-change-in-production")
    DEBUG = os.getenv("DEBUG", "true").lower() == "true"
