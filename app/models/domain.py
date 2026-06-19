"""
Internal domain models.

These dataclasses are the vocabulary the pipeline speaks in: a `Document` is an
uploaded file, a `Chunk` is a retrievable span of one document, and a
`ScoredChunk` is a chunk paired with a relevance score from some stage of
retrieval. Keeping these separate from the Pydantic API schemas (in
`app/models/schemas.py`) means the wire format can change without forcing a
rewrite of the engine, and vice versa.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def now_ts() -> float:
    return time.time()


@dataclass
class Document:
    """An ingested source file within a namespace."""
    id: str
    namespace: str
    filename: str
    content_type: str
    content_hash: str          # sha256 of raw bytes, used for dedup
    size_bytes: int
    char_count: int
    chunk_count: int
    created_at: float = field(default_factory=now_ts)
    title: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class Chunk:
    """A retrievable span of text belonging to a document."""
    id: str
    document_id: str
    namespace: str
    ordinal: int               # position of the chunk within its document
    text: str
    filename: str
    char_start: int
    char_end: int
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class ScoredChunk:
    """A chunk plus the score(s) assigned to it during retrieval.

    `score` is the active score for the current stage. The per-signal scores are
    retained so the API can expose *why* a chunk surfaced (useful for debugging
    and for the dashboard's retrieval inspector).
    """
    chunk: Chunk
    score: float = 0.0
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None
    fused_score: Optional[float] = None
    rerank_score: Optional[float] = None
    vector_rank: Optional[int] = None
    keyword_rank: Optional[int] = None


@dataclass
class Citation:
    """A reference attached to a generated answer."""
    marker: str                # e.g. "[1]"
    chunk_id: str
    document_id: str
    filename: str
    ordinal: int
    snippet: str
    score: float


@dataclass
class RagResult:
    """The full output of a query: answer, citations, and timing breakdown."""
    answer: str
    citations: List[Citation]
    used_chunks: List[ScoredChunk]
    model: str
    grounded: bool
    timings_ms: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
