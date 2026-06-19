"""
Query service.

The read path: take a natural-language question, run hybrid retrieval + rerank,
compose a grounded answer, log the outcome for analytics, and map everything
into the public ``QueryResponse`` schema.

The analytics write is best-effort and must never break a successful answer, so
it is wrapped defensively: telemetry failures are logged, not propagated.
"""
from __future__ import annotations

import time

from app.config import Settings
from app.core.rag import RagComposer
from app.core.retriever import Retriever
from app.logging_config import get_logger
from app.models.schemas import (
    CitationModel,
    QueryRequest,
    QueryResponse,
    RetrievedChunkModel,
)
from app.storage.analytics_store import AnalyticsStore

logger = get_logger("eka.query")


class QueryService:
    def __init__(
        self,
        settings: Settings,
        retriever: Retriever,
        rag: RagComposer,
        analytics: AnalyticsStore,
    ):
        self._s = settings
        self._retriever = retriever
        self._rag = rag
        self._analytics = analytics

    def answer(self, req: QueryRequest) -> QueryResponse:
        namespace = (req.namespace or "default").strip() or "default"
        started = time.perf_counter()

        scored, timings = self._retriever.retrieve(
            namespace=namespace,
            query=req.question,
            top_k=req.top_k,
            use_hybrid=req.hybrid,
            use_rerank=req.rerank,
        )
        result = self._rag.compose(
            question=req.question,
            chunks=scored,
            answer_style=req.answer_style,
            retrieval_timings=timings,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        result.timings_ms["total_ms"] = round(latency_ms, 2)

        # Best-effort telemetry.
        try:
            self._analytics.record_query(
                namespace=namespace,
                question=req.question,
                grounded=result.grounded,
                num_citations=len(result.citations),
                latency_ms=latency_ms,
                model=result.model,
                success=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception("analytics_record_failed")

        citations = [
            CitationModel(
                marker=c.marker,
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                filename=c.filename,
                ordinal=c.ordinal,
                snippet=c.snippet,
                score=c.score,
            )
            for c in result.citations
        ]

        chunks_out = None
        if req.include_chunks:
            chunks_out = [
                RetrievedChunkModel(
                    chunk_id=sc.chunk.id,
                    document_id=sc.chunk.document_id,
                    filename=sc.chunk.filename,
                    ordinal=sc.chunk.ordinal,
                    text=sc.chunk.text,
                    score=round(float(sc.score), 6),
                    vector_score=_round(sc.vector_score),
                    keyword_score=_round(sc.keyword_score),
                    fused_score=_round(sc.fused_score),
                    rerank_score=_round(sc.rerank_score),
                )
                for sc in result.used_chunks
            ]

        return QueryResponse(
            answer=result.answer,
            grounded=result.grounded,
            model=result.model,
            namespace=namespace,
            citations=citations,
            timings_ms={k: round(v, 2) for k, v in result.timings_ms.items()},
            warnings=result.warnings,
            chunks=chunks_out,
        )


def _round(v):
    return None if v is None else round(float(v), 6)
