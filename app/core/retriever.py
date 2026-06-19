"""
Retrieval orchestrator.

Runs the full first-stage + reranking pipeline and returns hydrated, scored
chunks ready to ground an answer:

    embed query
      -> vector search        (semantic)
      -> BM25 search          (lexical)        [if hybrid]
      -> fuse                 (RRF / weighted) [if hybrid]
      -> hydrate candidates   (chunk text from metadata store)
      -> rerank               (cross-encoder / heuristic) [if enabled]
      -> top-k

The retriever is decoupled from storage: it receives a ``chunk_lookup`` callable
so the engine never imports the SQLite layer directly.
"""
from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Sequence

from app.config import Settings
from app.core.embeddings.base import Embedder
from app.core.fusion import FusionHit, fuse
from app.core.keyword.bm25_index import BM25Index
from app.core.rerank.base import Reranker
from app.core.vectorstore.base import VectorStore
from app.logging_config import get_logger
from app.models.domain import Chunk, ScoredChunk

logger = get_logger("eka.retriever")

# (namespace, chunk_ids) -> {chunk_id: Chunk}
ChunkLookup = Callable[[str, Sequence[str]], Dict[str, Chunk]]


class Retriever:
    def __init__(
        self,
        settings: Settings,
        embedder: Embedder,
        vector_store: VectorStore,
        bm25_index: BM25Index,
        chunk_lookup: ChunkLookup,
        reranker: Optional[Reranker] = None,
    ):
        self._s = settings
        self._embedder = embedder
        self._vectors = vector_store
        self._bm25 = bm25_index
        self._lookup = chunk_lookup
        self._reranker = reranker

    def retrieve(
        self,
        namespace: str,
        query: str,
        top_k: Optional[int] = None,
        use_hybrid: Optional[bool] = None,
        use_rerank: Optional[bool] = None,
    ) -> tuple[List[ScoredChunk], Dict[str, float]]:
        s = self._s
        timings: Dict[str, float] = {}
        final_k = top_k or s.final_top_k
        hybrid = s.hybrid_enabled if use_hybrid is None else use_hybrid
        do_rerank = (self._reranker is not None) if use_rerank is None else (
            use_rerank and self._reranker is not None
        )

        # 1) Embed + vector search.
        t0 = time.perf_counter()
        q_vec = self._embedder.embed_query(query)
        timings["embed_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        vector_results = self._vectors.query(namespace, q_vec, s.vector_top_k)
        timings["vector_search_ms"] = (time.perf_counter() - t0) * 1000

        # 2) Keyword search (optional).
        keyword_results = []
        if hybrid and s.bm25_enabled:
            t0 = time.perf_counter()
            keyword_results = self._bm25.query(namespace, query, s.keyword_top_k)
            timings["keyword_search_ms"] = (time.perf_counter() - t0) * 1000

        # 3) Fuse, or fall back to vector ranking alone.
        t0 = time.perf_counter()
        if hybrid and keyword_results:
            hits: List[FusionHit] = fuse(
                vector_results,
                keyword_results,
                method=s.fusion_method,
                rrf_k=s.rrf_k,
                vector_weight=s.vector_weight,
                keyword_weight=s.keyword_weight,
            )
        else:
            hits = [
                FusionHit(
                    chunk_id=cid,
                    fused_score=score,
                    vector_score=score,
                    vector_rank=i + 1,
                )
                for i, (cid, score) in enumerate(vector_results)
            ]
        timings["fusion_ms"] = (time.perf_counter() - t0) * 1000

        if not hits:
            return [], timings

        # 4) Hydrate candidates (text comes from the metadata store).
        candidate_hits = hits[: max(s.rerank_candidates, final_k)]
        chunk_ids = [h.chunk_id for h in candidate_hits]
        chunk_map = self._lookup(namespace, chunk_ids)

        scored: List[ScoredChunk] = []
        for h in candidate_hits:
            chunk = chunk_map.get(h.chunk_id)
            if chunk is None:
                continue  # chunk was deleted since indexing; skip silently
            scored.append(
                ScoredChunk(
                    chunk=chunk,
                    score=h.fused_score,
                    vector_score=h.vector_score,
                    keyword_score=h.keyword_score,
                    fused_score=h.fused_score,
                    vector_rank=h.vector_rank,
                    keyword_rank=h.keyword_rank,
                )
            )

        # 5) Rerank (optional).
        if do_rerank and scored:
            t0 = time.perf_counter()
            ranked = self._reranker.rerank(
                query, [(sc.chunk.id, sc.chunk.text) for sc in scored]
            )
            rank_score = {cid: sc for cid, sc in ranked}
            order = {cid: i for i, (cid, _) in enumerate(ranked)}
            for sc in scored:
                sc.rerank_score = rank_score.get(sc.chunk.id)
                sc.score = sc.rerank_score if sc.rerank_score is not None else sc.score
            scored.sort(key=lambda sc: order.get(sc.chunk.id, 1_000_000))
            timings["rerank_ms"] = (time.perf_counter() - t0) * 1000

        result = scored[:final_k]
        logger.info(
            "retrieval_complete",
            extra={
                "namespace": namespace,
                "hybrid": hybrid,
                "reranked": do_rerank,
                "vector_hits": len(vector_results),
                "keyword_hits": len(keyword_results),
                "returned": len(result),
            },
        )
        return result, timings
