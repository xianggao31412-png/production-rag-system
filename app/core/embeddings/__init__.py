"""Embedder factory."""
from __future__ import annotations

from app.config import Settings
from app.core.embeddings.base import Embedder
from app.core.embeddings.hash_embedder import HashEmbedder
from app.core.embeddings.openai_compatible import OpenAICompatibleEmbedder


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider == "openai_compatible":
        return OpenAICompatibleEmbedder(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
            timeout=settings.embedding_timeout,
            batch_size=settings.embedding_batch_size,
        )
    return HashEmbedder(dim=settings.embedding_dim)


__all__ = ["Embedder", "build_embedder", "HashEmbedder", "OpenAICompatibleEmbedder"]
