"""
Admin / analytics service.

Aggregates read-only views for the dashboard and the admin API: catalogue
statistics, operational metrics, and the recent-query feed. It is a thin
read-side facade over the metadata store, the analytics store, and the live
component handles, so route handlers stay trivial.
"""
from __future__ import annotations

from typing import List, Optional

from app.config import Settings
from app.core.embeddings.base import Embedder
from app.core.llm import LLMClient
from app.core.vectorstore.base import VectorStore
from app.models.schemas import (
    ComponentStatus,
    MetricsResponse,
    NamespaceStat,
    QueryLogList,
    QueryLogModel,
    StatsResponse,
)
from app.storage.analytics_store import AnalyticsStore
from app.storage.metadata_store import MetadataStore


class AdminService:
    def __init__(
        self,
        settings: Settings,
        metadata_store: MetadataStore,
        analytics: AnalyticsStore,
        vector_store: VectorStore,
        embedder: Embedder,
        llm_client: Optional[LLMClient],
    ):
        self._s = settings
        self._meta = metadata_store
        self._analytics = analytics
        self._vectors = vector_store
        self._embedder = embedder
        self._llm = llm_client

    def stats(self) -> StatsResponse:
        total_docs, total_chunks = self._meta.counts()
        ns_rows = self._meta.namespace_stats()
        namespaces = [
            NamespaceStat(namespace=ns, documents=d, chunks=c) for ns, d, c in ns_rows
        ]
        return StatsResponse(
            total_documents=total_docs,
            total_chunks=total_chunks,
            total_queries=self._analytics.total_queries(),
            namespaces=namespaces,
            embedding_provider=self._s.embedding_provider,
            vector_backend=self._s.vector_backend,
            rerank_provider=self._s.rerank_provider,
            llm_model=self._s.llm_model if self._llm else "extractive-stub",
            llm_active=self._llm is not None,
        )

    def metrics(self) -> MetricsResponse:
        m = self._analytics.metrics()
        return MetricsResponse(**m)

    def recent_queries(self, limit: int = 50, offset: int = 0) -> QueryLogList:
        items, total = self._analytics.recent(limit=limit, offset=offset)
        return QueryLogList(
            total=total,
            items=[QueryLogModel(**it) for it in items],
        )

    def readiness(self) -> List[ComponentStatus]:
        components: List[ComponentStatus] = []

        # Vector store reachability.
        try:
            ok = self._vectors.ping()
            components.append(
                ComponentStatus(name="vector_store", ok=ok,
                                detail=self._s.vector_backend)
            )
        except Exception as exc:  # noqa: BLE001
            components.append(
                ComponentStatus(name="vector_store", ok=False, detail=str(exc))
            )

        # Embedder (dimension is a cheap, always-available property).
        try:
            dim = self._embedder.dimension
            components.append(
                ComponentStatus(name="embedder", ok=True,
                                detail=f"{self._s.embedding_provider} dim={dim}")
            )
        except Exception as exc:  # noqa: BLE001
            components.append(
                ComponentStatus(name="embedder", ok=False, detail=str(exc))
            )

        # LLM: stub mode is a valid, ready state.
        if self._llm is None:
            components.append(
                ComponentStatus(name="llm", ok=True, detail="extractive-stub (no network LLM)")
            )
        else:
            reachable = self._llm.ping()
            components.append(
                ComponentStatus(
                    name="llm",
                    ok=True,  # network LLM is optional; stub covers failures
                    detail=f"{self._s.llm_model} reachable={reachable}",
                )
            )
        return components
