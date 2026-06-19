"""Embedder interface shared by all embedding providers."""
from __future__ import annotations

import abc
from typing import List


class Embedder(abc.ABC):
    """Maps text to fixed-length, unit-normalised vectors."""

    name: str = "base"

    @property
    @abc.abstractmethod
    def dimension(self) -> int:
        ...

    @abc.abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of documents."""

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query. Defaults to the document path."""
        return self.embed_documents([text])[0]
