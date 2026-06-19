"""
Composition root / dependency container.

Everything is wired here, once, from a single ``Settings`` object, and stashed
on ``app.state.container``. Route handlers pull collaborators from the container
rather than constructing anything themselves, which keeps wiring in one place
and makes the whole graph trivially swappable in tests (build a container with
test settings, done).

Lifecycle:
    build()         -> construct the object graph (cheap; no network)
    rebuild_bm25()  -> repopulate the in-memory BM25 index from the durable
                       metadata store, because BM25 is not itself persisted
    shutdown()      -> flush the vector store and close DB connections
"""
from __future__ import annotations

import os

from app.config import Settings
from app.core.embeddings import build_embedder
from app.core.keyword.bm25_index import BM25Index
from app.core.llm import build_llm_client
from app.core.rag import RagComposer
from app.core.rerank import build_reranker
from app.core.retriever import Retriever
from app.core.vectorstore import build_vector_store
from app.logging_config import get_logger
from app.services.admin_service import AdminService
from app.services.ingest_service import IngestService
from app.services.query_service import QueryService
from app.storage.analytics_store import AnalyticsStore
from app.storage.metadata_store import MetadataStore

logger = get_logger("eka.container")


class Container:
    def __init__(self, settings: Settings):
        self.settings = settings

        os.makedirs(settings.data_dir, exist_ok=True)

        # ---- Core engine -------------------------------------------------
        self.embedder = build_embedder(settings)
        self.vector_store = build_vector_store(settings)
        self.bm25_index = BM25Index()
        self.reranker = build_reranker(settings)
        self.llm_client = build_llm_client(settings)

        # ---- Storage -----------------------------------------------------
        self.metadata_store = MetadataStore(os.path.join(settings.data_dir, "metadata.db"))
        self.analytics_store = AnalyticsStore(os.path.join(settings.data_dir, "analytics.db"))

        # ---- Retrieval + generation -------------------------------------
        self.retriever = Retriever(
            settings=settings,
            embedder=self.embedder,
            vector_store=self.vector_store,
            bm25_index=self.bm25_index,
            chunk_lookup=self.metadata_store.get_chunks,
            reranker=self.reranker,
        )
        self.rag = RagComposer(settings, self.llm_client)

        # ---- Services ----------------------------------------------------
        self.ingest_service = IngestService(
            settings=settings,
            embedder=self.embedder,
            vector_store=self.vector_store,
            bm25_index=self.bm25_index,
            metadata_store=self.metadata_store,
        )
        self.query_service = QueryService(
            settings=settings,
            retriever=self.retriever,
            rag=self.rag,
            analytics=self.analytics_store,
        )
        self.admin_service = AdminService(
            settings=settings,
            metadata_store=self.metadata_store,
            analytics=self.analytics_store,
            vector_store=self.vector_store,
            embedder=self.embedder,
            llm_client=self.llm_client,
        )

    @classmethod
    def build(cls, settings: Settings) -> "Container":
        c = cls(settings)
        c.rebuild_bm25()
        logger.info(
            "container_ready",
            extra={
                "embedding_provider": settings.embedding_provider,
                "vector_backend": settings.vector_backend,
                "rerank_provider": settings.rerank_provider,
                "llm_active": c.llm_client is not None,
            },
        )
        return c

    def rebuild_bm25(self) -> int:
        """Repopulate BM25 from the durable catalogue. Returns chunk count."""
        if not self.settings.bm25_enabled:
            return 0
        by_ns: dict[str, list[tuple[str, str]]] = {}
        for namespace, chunk_id, text in self.metadata_store.iter_all_chunks():
            by_ns.setdefault(namespace, []).append((chunk_id, text))
        total = 0
        for namespace, items in by_ns.items():
            self.bm25_index.add(namespace, items)
            total += len(items)
        if total:
            logger.info("bm25_rebuilt", extra={"chunks": total,
                                                "namespaces": len(by_ns)})
        return total

    def shutdown(self) -> None:
        try:
            self.vector_store.persist()
        except Exception:  # noqa: BLE001
            logger.exception("vector_persist_failed_on_shutdown")
        self.metadata_store.close()
        self.analytics_store.close()
        logger.info("container_shutdown_complete")
