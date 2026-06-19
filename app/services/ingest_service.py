"""
Ingestion service.

Orchestrates the write path for a single uploaded file:

    extract text  ->  hash (dedup check)  ->  chunk  ->  embed
        ->  write to vector store + BM25 index + metadata store

The three stores are kept consistent by writing the durable metadata store
*last*: if embedding or vector insertion fails, nothing is committed to the
catalogue, so a partially-indexed document never appears in listings. Dedup is
content-hash based and scoped to the namespace, so the same file uploaded twice
is a no-op that returns the existing document id.
"""
from __future__ import annotations

from app.config import Settings
from app.core.chunking import chunk_text
from app.core.embeddings.base import Embedder
from app.core.extraction import extract_text
from app.core.hashing import sha256_bytes
from app.core.keyword.bm25_index import BM25Index
from app.core.vectorstore.base import VectorStore
from app.errors import EmptyDocumentError
from app.logging_config import get_logger
from app.models.domain import Chunk, Document, new_id
from app.models.schemas import UploadResponse
from app.storage.metadata_store import MetadataStore

logger = get_logger("eka.ingest")


class IngestService:
    def __init__(
        self,
        settings: Settings,
        embedder: Embedder,
        vector_store: VectorStore,
        bm25_index: BM25Index,
        metadata_store: MetadataStore,
    ):
        self._s = settings
        self._embedder = embedder
        self._vectors = vector_store
        self._bm25 = bm25_index
        self._meta = metadata_store

    def ingest(
        self,
        raw: bytes,
        filename: str,
        content_type: str = "",
        namespace: str = "default",
        title: str | None = None,
    ) -> UploadResponse:
        namespace = (namespace or "default").strip() or "default"

        # 1) Extract text (raises UnsupportedFileTypeError / EmptyDocumentError).
        text, kind = extract_text(raw, filename, content_type)
        if not text.strip():
            raise EmptyDocumentError(f"No extractable text in '{filename}'.")

        # 2) Dedup by content hash within the namespace.
        content_hash = sha256_bytes(raw)
        existing = self._meta.get_document_by_hash(namespace, content_hash)
        if existing is not None:
            logger.info(
                "ingest_deduplicated",
                extra={"namespace": namespace, "file": filename,
                       "document_id": existing.id},
            )
            return UploadResponse(
                document_id=existing.id,
                namespace=namespace,
                filename=existing.filename,
                content_hash=content_hash,
                char_count=existing.char_count,
                chunk_count=existing.chunk_count,
                deduplicated=True,
            )

        # 3) Chunk.
        pieces = chunk_text(
            text,
            chunk_size=self._s.chunk_size,
            chunk_overlap=self._s.chunk_overlap,
            min_chunk_chars=self._s.min_chunk_chars,
        )
        if not pieces:
            raise EmptyDocumentError(f"'{filename}' produced no usable chunks.")

        doc_id = new_id("doc")
        chunks = [
            Chunk(
                id=new_id("ch"),
                document_id=doc_id,
                namespace=namespace,
                ordinal=i,
                text=p.text,
                filename=filename,
                char_start=p.char_start,
                char_end=p.char_end,
            )
            for i, p in enumerate(pieces)
        ]

        # 4) Embed (batched inside the embedder).
        vectors = self._embedder.embed_documents([c.text for c in chunks])
        if len(vectors) != len(chunks):
            raise EmptyDocumentError("Embedding count did not match chunk count.")

        # 5) Index into the vector store and BM25 index first (recoverable),
        #    then commit to the durable catalogue last.
        self._vectors.add(namespace, [(c.id, v) for c, v in zip(chunks, vectors)])
        if self._s.bm25_enabled:
            self._bm25.add(namespace, [(c.id, c.text) for c in chunks])

        document = Document(
            id=doc_id,
            namespace=namespace,
            filename=filename,
            content_type=content_type or kind,
            content_hash=content_hash,
            size_bytes=len(raw),
            char_count=len(text),
            chunk_count=len(chunks),
            title=title,
            metadata={"kind": kind},
        )
        self._meta.add_document(document, chunks)
        self._vectors.persist()

        logger.info(
            "ingest_complete",
            extra={"namespace": namespace, "file": filename,
                   "document_id": doc_id, "chunks": len(chunks),
                   "kind": kind},
        )
        return UploadResponse(
            document_id=doc_id,
            namespace=namespace,
            filename=filename,
            content_hash=content_hash,
            char_count=len(text),
            chunk_count=len(chunks),
            deduplicated=False,
        )

    # ------------------------------------------------------------------ #
    # Deletion (keeps all three stores in sync)
    # ------------------------------------------------------------------ #
    def delete_document(self, document_id: str):
        namespace, chunk_ids = self._meta.delete_document(document_id)
        deleted = 0
        if namespace is not None and chunk_ids:
            self._vectors.delete_chunks(namespace, chunk_ids)
            if self._s.bm25_enabled:
                self._bm25.delete_chunks(namespace, chunk_ids)
            self._vectors.persist()
            deleted = len(chunk_ids)
        return namespace, deleted
