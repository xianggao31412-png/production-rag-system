"""
In-memory vector store.

Holds vectors in numpy arrays per namespace and computes cosine similarity with
a single matrix multiply. Vectors are persisted to a pickle file so they survive
restarts. This backend needs no external services and is the default; it is
appropriate up to ~hundreds of thousands of chunks. Beyond that, switch
`VECTOR_BACKEND=chroma`.

Persistence is intentionally simple (full snapshot on flush). Writes are guarded
by a lock so concurrent ingests don't corrupt the in-memory maps.
"""
from __future__ import annotations

import os
import pickle
import threading
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.core.vectorstore.base import VectorStore
from app.logging_config import get_logger

logger = get_logger("eka.vectorstore.memory")


class MemoryVectorStore(VectorStore):
    name = "memory"

    def __init__(self, persist_path: Optional[str] = None):
        self._persist_path = persist_path
        self._lock = threading.RLock()
        # namespace -> {chunk_id: np.ndarray(float32)}
        self._store: Dict[str, Dict[str, np.ndarray]] = {}
        self._load()

    # ---- persistence ------------------------------------------------------
    def _load(self) -> None:
        if not self._persist_path or not os.path.exists(self._persist_path):
            return
        try:
            with open(self._persist_path, "rb") as fh:
                raw = pickle.load(fh)
            self._store = {
                ns: {cid: np.asarray(v, dtype=np.float32) for cid, v in items.items()}
                for ns, items in raw.items()
            }
            logger.info("vector_store_loaded", extra={"namespaces": len(self._store)})
        except Exception as exc:  # noqa: BLE001
            logger.error("vector_store_load_failed", extra={"error": str(exc)})
            self._store = {}

    def persist(self) -> None:
        if not self._persist_path:
            return
        with self._lock:
            os.makedirs(os.path.dirname(self._persist_path) or ".", exist_ok=True)
            tmp = f"{self._persist_path}.tmp"
            with open(tmp, "wb") as fh:
                snapshot = {
                    ns: {cid: v.tolist() for cid, v in items.items()}
                    for ns, items in self._store.items()
                }
                pickle.dump(snapshot, fh)
            os.replace(tmp, self._persist_path)  # atomic on POSIX & Windows

    # ---- helpers ----------------------------------------------------------
    @staticmethod
    def _normalise(vec: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec

    # ---- API --------------------------------------------------------------
    def add(self, namespace: str, items: Sequence[Tuple[str, List[float]]]) -> None:
        if not items:
            return
        with self._lock:
            bucket = self._store.setdefault(namespace, {})
            for chunk_id, vector in items:
                bucket[chunk_id] = self._normalise(np.asarray(vector, dtype=np.float32))

    def query(
        self, namespace: str, vector: List[float], top_k: int
    ) -> List[Tuple[str, float]]:
        with self._lock:
            bucket = self._store.get(namespace)
            if not bucket:
                return []
            ids = list(bucket.keys())
            matrix = np.vstack([bucket[i] for i in ids])  # (N, dim), unit rows
        q = self._normalise(np.asarray(vector, dtype=np.float32))
        if matrix.shape[1] != q.shape[0]:
            logger.error(
                "vector_dim_mismatch",
                extra={"store_dim": matrix.shape[1], "query_dim": q.shape[0]},
            )
            return []
        scores = matrix @ q  # cosine, since all rows and q are unit-norm
        k = min(top_k, len(ids))
        top_idx = np.argpartition(-scores, k - 1)[:k]
        top_idx = top_idx[np.argsort(-scores[top_idx])]
        return [(ids[i], float(scores[i])) for i in top_idx]

    def delete_chunks(self, namespace: str, chunk_ids: Sequence[str]) -> int:
        removed = 0
        with self._lock:
            bucket = self._store.get(namespace)
            if not bucket:
                return 0
            for cid in chunk_ids:
                if bucket.pop(cid, None) is not None:
                    removed += 1
            if not bucket:
                self._store.pop(namespace, None)
        return removed

    def count(self, namespace: Optional[str] = None) -> int:
        with self._lock:
            if namespace is not None:
                return len(self._store.get(namespace, {}))
            return sum(len(b) for b in self._store.values())

    def namespaces(self) -> List[str]:
        with self._lock:
            return sorted(self._store.keys())
