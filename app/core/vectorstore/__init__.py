"""Vector store factory."""
from __future__ import annotations

import os

from app.config import Settings
from app.core.vectorstore.base import VectorStore
from app.core.vectorstore.memory_store import MemoryVectorStore


def build_vector_store(settings: Settings) -> VectorStore:
    if settings.vector_backend == "chroma":
        from app.core.vectorstore.chroma_store import ChromaVectorStore
        return ChromaVectorStore(path=settings.chroma_path)
    persist_path = os.path.join(settings.data_dir, "vectorstore.pkl")
    return MemoryVectorStore(persist_path=persist_path)


__all__ = ["VectorStore", "build_vector_store", "MemoryVectorStore"]
