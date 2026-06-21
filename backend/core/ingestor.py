import os
import json
from datetime import datetime
from pathlib import Path
import pymupdf
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import Config

class DocumentIngestor:
    def __init__(self):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=Config.CHUNK_SIZE,
            chunk_overlap=Config.CHUNK_OVERLAP,
            separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
        )

    def extract_text(self, file_path: str, file_type: str) -> str:
        """Extract raw text from any supported file type."""
        try:
            if file_type == "pdf":
                return self._extract_pdf(file_path)
            elif file_type in ["txt", "md", "markdown"]:
                return self._extract_text_file(file_path)
            elif file_type == "json":
                return self._extract_json(file_path)
            else:
                raise ValueError(f"Unsupported file type: {file_type}")
        except Exception as e:
            raise Exception(f"Extraction failed: {str(e)}")

    def _extract_pdf(self, file_path: str) -> str:
        doc = pymupdf.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
        return text.strip()

    def _extract_text_file(self, file_path: str) -> str:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read().strip()

    def _extract_json(self, file_path: str) -> str:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return "\n".join([str(item) for item in data])
        return json.dumps(data, indent=2)

    def chunk_text(self, text: str) -> list[str]:
        """Split text into chunks for embedding."""
        chunks = self.splitter.split_text(text)
        return [c.strip() for c in chunks if len(c.strip()) > 50]

    def get_file_type(self, filename: str) -> str:
        ext = Path(filename).suffix.lower().lstrip('.')
        type_map = {
            'pdf': 'pdf',
            'txt': 'txt',
            'md': 'md',
            'markdown': 'md',
            'json': 'json'
        }
        return type_map.get(ext, 'unknown')

    def get_word_count(self, text: str) -> int:
        return len(text.split())
