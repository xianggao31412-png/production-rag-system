"""
Deterministic hashing embedder.

A dependency-free embedder built on the *hashing trick*: each token (and each
character 3-gram, to capture sub-word similarity) is hashed into one of
`dimension` buckets and its weight accumulated. The vector is L2-normalised so
dot product equals cosine similarity.

This is **not** a semantic model — it captures lexical overlap, not meaning. Its
job is to let the whole pipeline run, be tested, and be demoed with zero model
downloads. For real semantic retrieval, switch `EMBEDDING_PROVIDER` to
`openai_compatible` and point it at a local embedding model (e.g. nomic-embed-text
via Ollama).
"""
from __future__ import annotations

import math
import re
from typing import List

from app.core.embeddings.base import Embedder

_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _hash(token: str, salt: str, dim: int) -> int:
    # Stable, process-independent bucket (Python's hash() is salted per run).
    h = 1469598103934665603
    for ch in salt + "\x00" + token:
        h ^= ord(ch)
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h % dim


class HashEmbedder(Embedder):
    name = "hash"

    def __init__(self, dim: int = 384):
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def _embed_one(self, text: str) -> List[float]:
        vec = [0.0] * self._dim
        tokens = _TOKEN.findall(text.lower())
        for tok in tokens:
            vec[_hash(tok, "tok", self._dim)] += 1.0
            # Character 3-grams give partial credit for shared sub-words.
            padded = f"#{tok}#"
            for i in range(len(padded) - 2):
                gram = padded[i : i + 3]
                vec[_hash(gram, "gram", self._dim)] += 0.5
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]
