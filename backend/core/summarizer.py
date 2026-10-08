from langchain_ollama import OllamaLLM
from config import Config


class Summarizer:
    def __init__(self):
        self.llm = OllamaLLM(
            model=Config.LLM_MODEL,
            base_url=Config.OLLAMA_BASE_URL,
            temperature=0.3
        )

    def summarize(self, text: str) -> str:
        """Generate a concise summary of a document."""
        truncated = text[:4000]
        prompt = f"""Summarize the following document concisely in 3-5 sentences.
Focus on the main topic, key points, and conclusions.

Document:
{truncated}

Summary:"""
        return self.llm.invoke(prompt).strip()

    def extract_tags(self, text: str) -> list[str]:
        """Auto-extract relevant tags from document."""
        truncated = text[:3000]
        prompt = f"""Extract 3-6 relevant topic tags from this document.
Return ONLY a comma-separated list of single words or short phrases.
Example: machine learning, python, data science, neural networks

Document:
{truncated}

Tags:"""
        response = self.llm.invoke(prompt).strip()
        tags = [t.strip().lower() for t in response.split(",")]
        return [t for t in tags if t and len(t) < 30][:6]

    def _extract_list(self, text: str, instruction: str, label: str) -> list[str]:
        """Shared implementation for action items / decisions / ideas.

        UPGRADE: these three were near-identical functions differing only in
        the prompt wording. Collapsed into one helper — same behavior, ~40
        fewer lines, and one place to fix parsing bugs instead of three.
        """
        truncated = text[:3000]
        prompt = f"""{instruction}
Return each on a new line starting with "- ".
If none exist, return "None".

Document:
{truncated}

{label}:"""
        response = self.llm.invoke(prompt).strip()
        if response.lower() == "none":
            return []
        items = [line.lstrip("- ").strip()
                 for line in response.split("\n")
                 if line.strip().startswith("-")]
        return items[:10]

    def extract_action_items(self, text: str) -> list[str]:
        return self._extract_list(
            text,
            "Extract any action items, tasks, or to-dos from this document.",
            "Action Items"
        )

    def extract_key_decisions(self, text: str) -> list[str]:
        return self._extract_list(
            text,
            "Extract any key decisions, conclusions, or important choices mentioned in this document.",
            "Key Decisions"
        )

    def extract_key_ideas(self, text: str) -> list[str]:
        return self._extract_list(
            text,
            "Extract the most important ideas, concepts, or frameworks from this document.",
            "Key Ideas"
        )

    def answer_query(self, query: str, context_chunks: list[dict]) -> str:
        """Answer a query using retrieved context (non-streaming)."""
        if not context_chunks:
            return "I couldn't find relevant information in your knowledge base for this query."

        prompt = self._build_answer_prompt(query, context_chunks)
        return self.llm.invoke(prompt).strip()

    def stream_answer(self, query: str, context_chunks: list[dict]):
        """Answer a query, yielding tokens as they're generated.

        UPGRADE: answer_query() blocked until the full response was ready —
        on llama3.1:8b that's a long silent wait before anything appears.
        This yields tokens as Ollama produces them, for the SSE endpoint.
        """
        if not context_chunks:
            yield "I couldn't find relevant information in your knowledge base for this query."
            return

        prompt = self._build_answer_prompt(query, context_chunks)
        for chunk in self.llm.stream(prompt):
            yield chunk

    def _build_answer_prompt(self, query: str, context_chunks: list[dict]) -> str:
        context = "\n\n---\n\n".join([
            f"From '{c['title']}':\n{c['content']}"
            for c in context_chunks[:5]
        ])

        return f"""You are MindVault, a personal AI memory assistant.
Answer the question using ONLY the provided context from the user's knowledge base.
If the answer isn't in the context, say "I don't have information about this in your knowledge base."
Always mention which document the information came from.

Context:
{context}

Question: {query}

Answer:"""
