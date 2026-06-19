"""
BM25 keyword index.

Maintains a BM25Okapi index per namespace over chunk texts. BM25 idf is computed
at construction time, so the index is marked dirty on add/delete and rebuilt
lazily on the next query. Texts are tokenised with a light lowercase word
tokeniser and a small English stopword filter.

This is the lexical half of hybrid retrieval: it reliably catches exact terms,
identifiers, and acronyms that embeddings sometimes wash out.
"""
from __future__ import annotations

import re
import threading
from typing import Dict, List, Sequence, Tuple

from rank_bm25 import BM25Okapi

from app.logging_config import get_logger

logger = get_logger("eka.keyword.bm25")

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "was", "were", "be", "been", "with", "as", "at", "by", "this", "that",
    "it", "from", "we", "you", "your", "our", "i", "do", "does", "how", "what",
    "which", "who", "can", "will", "may", "if", "not",
}


def tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS]


class _NamespaceIndex:
    def __init__(self) -> None:
        self.chunk_ids: List[str] = []
        self.tokens: List[List[str]] = []
        self._bm25: BM25Okapi | None = None
        self._dirty = True

    def add(self, chunk_id: str, text: str) -> None:
        self.chunk_ids.append(chunk_id)
        self.tokens.append(tokenize(text))
        self._dirty = True

    def remove(self, chunk_ids: set) -> int:
        keep_ids, keep_tokens, removed = [], [], 0
        for cid, toks in zip(self.chunk_ids, self.tokens):
            if cid in chunk_ids:
                removed += 1
            else:
                keep_ids.append(cid)
                keep_tokens.append(toks)
        self.chunk_ids, self.tokens = keep_ids, keep_tokens
        if removed:
            self._dirty = True
        return removed

    def _ensure(self) -> None:
        if self._dirty:
            self._bm25 = BM25Okapi(self.tokens) if self.tokens else None
            self._dirty = False

    def query(self, q_tokens: List[str], top_k: int) -> List[Tuple[str, float]]:
        self._ensure()
        if self._bm25 is None or not q_tokens or not self.chunk_ids:
            return []
        scores = self._bm25.get_scores(q_tokens)
        # Keep chunks that share at least one query term. We deliberately do NOT
        # filter on score > 0: on a small corpus BM25Okapi's idf turns negative
        # for terms present in most documents, which would otherwise discard
        # every genuine match. RRF (the default fusion) ranks by order, so the
        # absolute score sign is irrelevant — real lexical overlap is the signal.
        q_set = set(q_tokens)
        candidates = [
            (cid, float(s))
            for cid, toks, s in zip(self.chunk_ids, self.tokens, scores)
            if q_set.intersection(toks)
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_k]

    def count(self) -> int:
        return len(self.chunk_ids)


class BM25Index:
    """Thread-safe collection of per-namespace BM25 indexes."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._indexes: Dict[str, _NamespaceIndex] = {}

    def add(self, namespace: str, items: Sequence[Tuple[str, str]]) -> None:
        """items = [(chunk_id, text), ...]"""
        if not items:
            return
        with self._lock:
            idx = self._indexes.setdefault(namespace, _NamespaceIndex())
            for chunk_id, text in items:
                idx.add(chunk_id, text)

    def query(self, namespace: str, query: str, top_k: int) -> List[Tuple[str, float]]:
        with self._lock:
            idx = self._indexes.get(namespace)
            if idx is None:
                return []
            return idx.query(tokenize(query), top_k)

    def delete_chunks(self, namespace: str, chunk_ids: Sequence[str]) -> int:
        with self._lock:
            idx = self._indexes.get(namespace)
            if idx is None:
                return 0
            removed = idx.remove(set(chunk_ids))
            if idx.count() == 0:
                self._indexes.pop(namespace, None)
            return removed

    def count(self, namespace: str | None = None) -> int:
        with self._lock:
            if namespace is not None:
                idx = self._indexes.get(namespace)
                return idx.count() if idx else 0
            return sum(i.count() for i in self._indexes.values())

    def namespaces(self) -> List[str]:
        with self._lock:
            return sorted(self._indexes.keys())
