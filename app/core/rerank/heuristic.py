"""
Heuristic reranker.

A dependency-free reranker that scores each candidate by how well it covers the
query's terms: the fraction of distinct query tokens present, a bonus for
contiguous query phrases appearing verbatim, and a mild penalty for very long
chunks (which dilute relevance). It won't match a trained cross-encoder, but it
meaningfully improves ordering over raw fusion at zero cost, and keeps the
default install light.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

from app.core.keyword.bm25_index import tokenize
from app.core.rerank.base import Reranker


class HeuristicReranker(Reranker):
    name = "heuristic"

    def _score(self, q_tokens: List[str], q_set: set, text: str) -> float:
        if not q_set:
            return 0.0
        c_tokens = tokenize(text)
        if not c_tokens:
            return 0.0
        c_set = set(c_tokens)

        coverage = len(q_set & c_set) / len(q_set)

        # Phrase bonus: reward verbatim bigrams from the query.
        lowered = text.lower()
        bigram_hits = 0
        for i in range(len(q_tokens) - 1):
            if f"{q_tokens[i]} {q_tokens[i + 1]}" in lowered:
                bigram_hits += 1
        phrase_bonus = min(0.3, 0.1 * bigram_hits)

        # Term frequency saturation (diminishing returns).
        tf = sum(1 for t in c_tokens if t in q_set)
        tf_component = tf / (tf + 4.0)

        # Length penalty: prefer focused passages.
        length_penalty = 1.0 / (1.0 + max(0, len(c_tokens) - 180) / 400.0)

        return (0.65 * coverage + 0.2 * tf_component + phrase_bonus) * length_penalty

    def rerank(
        self, query: str, candidates: Sequence[Tuple[str, str]]
    ) -> List[Tuple[str, float]]:
        q_tokens = tokenize(query)
        q_set = set(q_tokens)
        scored = [(cid, self._score(q_tokens, q_set, text)) for cid, text in candidates]
        return sorted(scored, key=lambda x: x[1], reverse=True)
