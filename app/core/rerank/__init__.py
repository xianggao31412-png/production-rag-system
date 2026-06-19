"""Reranker factory."""
from __future__ import annotations

from typing import Optional

from app.config import Settings
from app.core.rerank.base import Reranker
from app.core.rerank.heuristic import HeuristicReranker


def build_reranker(settings: Settings) -> Optional[Reranker]:
    """Return a reranker, or None when reranking is disabled."""
    if settings.rerank_provider == "none":
        return None
    if settings.rerank_provider == "cross_encoder":
        from app.core.rerank.cross_encoder import CrossEncoderReranker
        return CrossEncoderReranker(settings.rerank_model)
    return HeuristicReranker()


__all__ = ["Reranker", "build_reranker", "HeuristicReranker"]
