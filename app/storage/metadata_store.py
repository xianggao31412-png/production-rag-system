"""
Metadata store (SQLite).

The durable source of truth for documents and their chunks. The vector store and
BM25 index hold only ids and derived structures; the canonical chunk text,
document records, and namespace bookkeeping live here.

Why SQLite: it is zero-ops, embedded, transactional, and more than adequate for
the single-node scope of this platform. The schema is small and the access
patterns are simple key/range lookups. WAL mode is enabled for better read/write
concurrency, and a process-wide lock serialises writes so the threadpool that
FastAPI runs sync handlers in cannot race.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Dict, List, Optional, Sequence, Tuple

from app.logging_config import get_logger
from app.models.domain import Chunk, Document

logger = get_logger("eka.storage.metadata")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id           TEXT PRIMARY KEY,
    namespace    TEXT NOT NULL,
    filename     TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL,
    char_count   INTEGER NOT NULL,
    chunk_count  INTEGER NOT NULL,
    title        TEXT,
    metadata     TEXT NOT NULL DEFAULT '{}',
    created_at   REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_doc_ns_hash ON documents(namespace, content_hash);
CREATE INDEX IF NOT EXISTS idx_doc_ns ON documents(namespace);

CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    namespace   TEXT NOT NULL,
    ordinal     INTEGER NOT NULL,
    text        TEXT NOT NULL,
    filename    TEXT NOT NULL,
    char_start  INTEGER NOT NULL,
    char_end    INTEGER NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chunk_ns ON chunks(namespace);
CREATE INDEX IF NOT EXISTS idx_chunk_doc ON chunks(document_id);
"""


class MetadataStore:
    def __init__(self, db_path: str):
        self._path = db_path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        logger.info("metadata_store_ready", extra={"path": db_path})

    # ---- row mapping ------------------------------------------------------
    @staticmethod
    def _to_document(row: sqlite3.Row) -> Document:
        return Document(
            id=row["id"],
            namespace=row["namespace"],
            filename=row["filename"],
            content_type=row["content_type"],
            content_hash=row["content_hash"],
            size_bytes=row["size_bytes"],
            char_count=row["char_count"],
            chunk_count=row["chunk_count"],
            title=row["title"],
            metadata=json.loads(row["metadata"] or "{}"),
            created_at=row["created_at"],
        )

    @staticmethod
    def _to_chunk(row: sqlite3.Row) -> Chunk:
        return Chunk(
            id=row["id"],
            document_id=row["document_id"],
            namespace=row["namespace"],
            ordinal=row["ordinal"],
            text=row["text"],
            filename=row["filename"],
            char_start=row["char_start"],
            char_end=row["char_end"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    # ---- writes -----------------------------------------------------------
    def add_document(self, document: Document, chunks: Sequence[Chunk]) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO documents
                   (id, namespace, filename, content_type, content_hash, size_bytes,
                    char_count, chunk_count, title, metadata, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    document.id, document.namespace, document.filename,
                    document.content_type, document.content_hash, document.size_bytes,
                    document.char_count, document.chunk_count, document.title,
                    json.dumps(document.metadata), document.created_at,
                ),
            )
            self._conn.executemany(
                """INSERT INTO chunks
                   (id, document_id, namespace, ordinal, text, filename,
                    char_start, char_end, metadata)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        c.id, c.document_id, c.namespace, c.ordinal, c.text,
                        c.filename, c.char_start, c.char_end, json.dumps(c.metadata),
                    )
                    for c in chunks
                ],
            )
            self._conn.commit()

    def delete_document(self, document_id: str) -> Tuple[Optional[str], List[str]]:
        """Delete a document and its chunks.

        Returns (namespace, chunk_ids) so the caller can purge the vector store
        and BM25 index. Returns (None, []) if the document does not exist.
        """
        with self._lock:
            doc = self._conn.execute(
                "SELECT namespace FROM documents WHERE id=?", (document_id,)
            ).fetchone()
            if doc is None:
                return None, []
            namespace = doc["namespace"]
            rows = self._conn.execute(
                "SELECT id FROM chunks WHERE document_id=?", (document_id,)
            ).fetchall()
            chunk_ids = [r["id"] for r in rows]
            self._conn.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
            self._conn.execute("DELETE FROM documents WHERE id=?", (document_id,))
            self._conn.commit()
            return namespace, chunk_ids

    # ---- reads ------------------------------------------------------------
    def get_document_by_hash(self, namespace: str, content_hash: str) -> Optional[Document]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM documents WHERE namespace=? AND content_hash=?",
                (namespace, content_hash),
            ).fetchone()
        return self._to_document(row) if row else None

    def get_document(self, document_id: str) -> Optional[Document]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM documents WHERE id=?", (document_id,)
            ).fetchone()
        return self._to_document(row) if row else None

    def list_documents(
        self, namespace: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> Tuple[List[Document], int]:
        with self._lock:
            if namespace:
                total = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM documents WHERE namespace=?", (namespace,)
                ).fetchone()["c"]
                rows = self._conn.execute(
                    "SELECT * FROM documents WHERE namespace=? "
                    "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (namespace, limit, offset),
                ).fetchall()
            else:
                total = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM documents"
                ).fetchone()["c"]
                rows = self._conn.execute(
                    "SELECT * FROM documents ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
        return [self._to_document(r) for r in rows], int(total)

    def get_chunks(self, namespace: str, chunk_ids: Sequence[str]) -> Dict[str, Chunk]:
        """The chunk_lookup used by the retriever to hydrate candidates."""
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" for _ in chunk_ids)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM chunks WHERE namespace=? AND id IN ({placeholders})",
                (namespace, *chunk_ids),
            ).fetchall()
        return {r["id"]: self._to_chunk(r) for r in rows}

    def iter_all_chunks(self) -> List[Tuple[str, str, str]]:
        """Return (namespace, chunk_id, text) for rebuilding the BM25 index."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT namespace, id, text FROM chunks"
            ).fetchall()
        return [(r["namespace"], r["id"], r["text"]) for r in rows]

    # ---- stats ------------------------------------------------------------
    def counts(self) -> Tuple[int, int]:
        with self._lock:
            docs = self._conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
            chunks = self._conn.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()["c"]
        return int(docs), int(chunks)

    def namespace_stats(self) -> List[Tuple[str, int, int]]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT d.namespace AS ns,
                          COUNT(DISTINCT d.id) AS docs,
                          COALESCE(SUM(d.chunk_count), 0) AS chunks
                   FROM documents d GROUP BY d.namespace ORDER BY d.namespace"""
            ).fetchall()
        return [(r["ns"], int(r["docs"]), int(r["chunks"])) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
