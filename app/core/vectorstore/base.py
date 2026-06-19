"""Vector store interface.

A vector store maps chunk ids to embedding vectors within a namespace and
answers nearest-neighbour queries by cosine similarity. Chunk *text* and
metadata live in the SQLite metadata store, not here — this layer only deals in
ids and vectors, which keeps the swap between the in-memory backend and Chroma
trivial.
"""
from __future__ import annotations

import abc
from typing import List, Optional, Sequence, Tuple


class VectorStore(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def add(self, namespace: str, items: Sequence[Tuple[str, List[float]]]) -> None:
        """Insert (chunk_id, vector) pairs into a namespace."""

    @abc.abstractmethod
    def query(
        self, namespace: str, vector: List[float], top_k: int
    ) -> List[Tuple[str, float]]:
        """Return up to ``top_k`` (chunk_id, cosine_score) pairs, best first."""

    @abc.abstractmethod
    def delete_chunks(self, namespace: str, chunk_ids: Sequence[str]) -> int:
        """Remove the given chunk ids from a namespace. Returns count removed."""

    @abc.abstractmethod
    def count(self, namespace: Optional[str] = None) -> int:
        ...

    @abc.abstractmethod
    def namespaces(self) -> List[str]:
        ...

    def persist(self) -> None:
        """Flush to durable storage. No-op for backends that auto-persist."""

    def ping(self) -> bool:
        """Lightweight readiness check."""
        return True
