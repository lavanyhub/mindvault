import chromadb
from chromadb.config import Settings
from langchain_ollama import OllamaEmbeddings
from config import Config
import os

class VectorStore:
    def __init__(self):
        os.makedirs(Config.CHROMA_PATH, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=Config.CHROMA_PATH,
        )
        self.collection = self.client.get_or_create_collection(
            name="mindvault",
            metadata={"hnsw:space": "cosine"}
        )
        self.embedder = OllamaEmbeddings(
            model=Config.EMBED_MODEL,
            base_url=Config.OLLAMA_BASE_URL
        )

      def add_chunks(self, doc_id: int, chunks: list[str], title: str, batch_size: int = 32):
        """Embed and store chunks in ChromaDB (idempotent, batched)."""
        if not chunks:
            return
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            embeddings = self.embedder.embed_documents(batch)
            self.collection.upsert(
                ids=[f"doc_{doc_id}_chunk_{start + i}" for i in range(len(batch))],
                embeddings=embeddings,
                documents=batch,
                metadatas=[{"doc_id": doc_id, "title": title, "chunk_index": start + i}
                           for i in range(len(batch))]
            )
        print(f"Added {len(chunks)} chunks for doc_id={doc_id}")

    def search(self, query: str, top_k: int = None) -> list[dict]:
        """Semantic search over all stored chunks."""
        # FIX (Phase 2.5): an empty collection made count()==0, and
        # `or 1` turned that into n_results=1 — so Chroma was queried for
        # 1 result over zero vectors instead of being skipped, which some
        # Chroma versions raise on. Explicit early return instead.
        if self.collection.count() == 0:
            return []

        top_k = top_k or Config.TOP_K_RESULTS
        query_embedding = self.embedder.embed_query(query)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.collection.count()),
            include=["documents", "metadatas", "distances"]
        )

        output = []
        for i, doc in enumerate(results["documents"][0]):
            distance = results["distances"][0][i]
            score = 1 - distance
            if score >= Config.MIN_RELEVANCE_SCORE:
                output.append({
                    "content": doc,
                    "doc_id": results["metadatas"][0][i]["doc_id"],
                    "title": results["metadatas"][0][i]["title"],
                    "score": round(score, 3)
                })

        return sorted(output, key=lambda x: x["score"], reverse=True)

    def delete_document(self, doc_id: int):
        """Remove all chunks for a document."""
        existing = self.collection.get(
            where={"doc_id": doc_id}
        )
        if existing["ids"]:
            self.collection.delete(ids=existing["ids"])
            print(f"✅ Deleted chunks for doc_id={doc_id}")

    def get_total_chunks(self) -> int:
        return self.collection.count()
