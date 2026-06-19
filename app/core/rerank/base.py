"""Reranker interface.

A reranker re-scores a small candidate set against the query with a more
expensive, more precise relevance function than first-stage retrieval. Input is
a list of (chunk_id, text); output is the same ids re-scored and sorted best
first.
"""
from __future__ import annotations

import abc
from typing import List, Sequence, Tuple


class Reranker(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def rerank(
        self, query: str, candidates: Sequence[Tuple[str, str]]
    ) -> List[Tuple[str, float]]:
        """Return (chunk_id, score) pairs sorted by descending relevance."""
