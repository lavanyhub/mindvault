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

    def add_chunks(self, doc_id: int, chunks: list[str], title: str):
        """Embed and store chunks in ChromaDB."""
        if not chunks:
            return

        embeddings = self.embedder.embed_documents(chunks)

        ids = [f"doc_{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [{"doc_id": doc_id, "title": title, "chunk_index": i}
                     for i in range(len(chunks))]

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas
        )
        print(f"✅ Added {len(chunks)} chunks for doc_id={doc_id}")

    def search(self, query: str, top_k: int = None) -> list[dict]:
        """Semantic search over all stored chunks."""
        top_k = top_k or Config.TOP_K_RESULTS
        query_embedding = self.embedder.embed_query(query)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.collection.count() or 1),
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
