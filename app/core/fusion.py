"""
Result fusion.

Combines the ranked lists from vector search and BM25 into a single ranking.

- ``rrf`` (Reciprocal Rank Fusion): rank-based, scale-free, and robust to the
  fact that cosine scores and BM25 scores live on different scales. Recommended.
- ``weighted``: min-max normalise each list's scores to [0, 1] and blend with
  configurable weights. More tunable, but sensitive to score distributions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class FusionHit:
    chunk_id: str
    fused_score: float
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None
    vector_rank: Optional[int] = None
    keyword_rank: Optional[int] = None


def _rank_map(results: List[Tuple[str, float]]) -> Dict[str, int]:
    """chunk_id -> 1-based rank."""
    return {cid: i + 1 for i, (cid, _) in enumerate(results)}


def _score_map(results: List[Tuple[str, float]]) -> Dict[str, float]:
    return {cid: s for cid, s in results}


def _minmax(scores: Dict[str, float]) -> Dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def reciprocal_rank_fusion(
    vector_results: List[Tuple[str, float]],
    keyword_results: List[Tuple[str, float]],
    k: int = 60,
) -> List[FusionHit]:
    v_rank = _rank_map(vector_results)
    k_rank = _rank_map(keyword_results)
    v_score = _score_map(vector_results)
    k_score = _score_map(keyword_results)

    hits: Dict[str, FusionHit] = {}
    for cid in set(v_rank) | set(k_rank):
        score = 0.0
        if cid in v_rank:
            score += 1.0 / (k + v_rank[cid])
        if cid in k_rank:
            score += 1.0 / (k + k_rank[cid])
        hits[cid] = FusionHit(
            chunk_id=cid,
            fused_score=score,
            vector_score=v_score.get(cid),
            keyword_score=k_score.get(cid),
            vector_rank=v_rank.get(cid),
            keyword_rank=k_rank.get(cid),
        )
    return sorted(hits.values(), key=lambda h: h.fused_score, reverse=True)


def weighted_fusion(
    vector_results: List[Tuple[str, float]],
    keyword_results: List[Tuple[str, float]],
    vector_weight: float = 0.5,
    keyword_weight: float = 0.5,
) -> List[FusionHit]:
    v_score = _score_map(vector_results)
    k_score = _score_map(keyword_results)
    v_rank = _rank_map(vector_results)
    k_rank = _rank_map(keyword_results)
    v_norm = _minmax(v_score)
    k_norm = _minmax(k_score)

    hits: Dict[str, FusionHit] = {}
    for cid in set(v_norm) | set(k_norm):
        score = vector_weight * v_norm.get(cid, 0.0) + keyword_weight * k_norm.get(cid, 0.0)
        hits[cid] = FusionHit(
            chunk_id=cid,
            fused_score=score,
            vector_score=v_score.get(cid),
            keyword_score=k_score.get(cid),
            vector_rank=v_rank.get(cid),
            keyword_rank=k_rank.get(cid),
        )
    return sorted(hits.values(), key=lambda h: h.fused_score, reverse=True)


def fuse(
    vector_results: List[Tuple[str, float]],
    keyword_results: List[Tuple[str, float]],
    method: str = "rrf",
    rrf_k: int = 60,
    vector_weight: float = 0.5,
    keyword_weight: float = 0.5,
) -> List[FusionHit]:
    if method == "weighted":
        return weighted_fusion(vector_results, keyword_results, vector_weight, keyword_weight)
    return reciprocal_rank_fusion(vector_results, keyword_results, rrf_k)
