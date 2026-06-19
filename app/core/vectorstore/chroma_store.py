"""
ChromaDB vector store (optional).

Used when `VECTOR_BACKEND=chroma`. Requires `pip install chromadb`. Each
namespace maps to a Chroma collection. Cosine distance is converted to a
similarity score in [0, 1] so the rest of the pipeline sees the same score
convention as the in-memory backend (higher is better).

Chroma persists automatically to `CHROMA_PATH`, so `persist()` is a no-op here.
"""
from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

from app.core.vectorstore.base import VectorStore
from app.errors import UpstreamError
from app.logging_config import get_logger

logger = get_logger("eka.vectorstore.chroma")

_SAFE = re.compile(r"[^a-zA-Z0-9_-]")


def _collection_name(namespace: str) -> str:
    # Chroma collection names must be 3-63 chars, alnum/_/-, start & end alnum.
    safe = _SAFE.sub("_", namespace).strip("_") or "default"
    name = f"ns_{safe}"
    return name[:63]


class ChromaVectorStore(VectorStore):
    name = "chroma"

    def __init__(self, path: str):
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
        except ImportError as exc:  # pragma: no cover - optional dep
            raise UpstreamError(
                "VECTOR_BACKEND=chroma requires chromadb. Install it with "
                "`pip install chromadb`, or set VECTOR_BACKEND=memory."
            ) from exc

        self._client = chromadb.PersistentClient(
            path=path, settings=ChromaSettings(anonymized_telemetry=False)
        )
        logger.info("chroma_client_ready", extra={"path": path})

    def _collection(self, namespace: str):
        return self._client.get_or_create_collection(
            name=_collection_name(namespace),
            metadata={"hnsw:space": "cosine", "eka_namespace": namespace},
        )

    def add(self, namespace: str, items: Sequence[Tuple[str, List[float]]]) -> None:
        if not items:
            return
        col = self._collection(namespace)
        ids = [cid for cid, _ in items]
        vecs = [v for _, v in items]
        col.upsert(ids=ids, embeddings=vecs)

    def query(
        self, namespace: str, vector: List[float], top_k: int
    ) -> List[Tuple[str, float]]:
        col = self._collection(namespace)
        n = col.count()
        if n == 0:
            return []
        res = col.query(query_embeddings=[vector], n_results=min(top_k, n))
        ids = (res.get("ids") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out: List[Tuple[str, float]] = []
        for cid, dist in zip(ids, dists):
            # cosine distance in [0, 2] -> similarity in [-1, 1]; clamp to [0,1].
            sim = 1.0 - float(dist)
            out.append((cid, max(0.0, sim)))
        return out

    def delete_chunks(self, namespace: str, chunk_ids: Sequence[str]) -> int:
        if not chunk_ids:
            return 0
        col = self._collection(namespace)
        col.delete(ids=list(chunk_ids))
        return len(chunk_ids)

    def count(self, namespace: Optional[str] = None) -> int:
        if namespace is not None:
            return self._collection(namespace).count()
        total = 0
        for col in self._client.list_collections():
            total += self._client.get_collection(col.name).count()
        return total

    def namespaces(self) -> List[str]:
        names = []
        for col in self._client.list_collections():
            meta = getattr(col, "metadata", None) or {}
            names.append(meta.get("eka_namespace", col.name))
        return sorted(set(names))

    def ping(self) -> bool:
        try:
            self._client.heartbeat()
            return True
        except Exception:  # noqa: BLE001
            return False
