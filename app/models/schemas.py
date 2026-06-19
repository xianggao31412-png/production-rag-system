"""
Public API schemas (the wire contract).

Every request body and response body that crosses the HTTP boundary is defined
here as a Pydantic model. FastAPI uses these for validation and for the
auto-generated OpenAPI docs at /docs.
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #
class UploadResponse(BaseModel):
    document_id: str
    namespace: str
    filename: str
    content_hash: str
    char_count: int
    chunk_count: int
    deduplicated: bool = Field(
        description="True if an identical file already existed; no new chunks were created."
    )


class DocumentSummary(BaseModel):
    id: str
    namespace: str
    filename: str
    content_type: str
    char_count: int
    chunk_count: int
    size_bytes: int
    created_at: float
    title: Optional[str] = None


class DocumentList(BaseModel):
    namespace: Optional[str] = None
    total: int
    documents: List[DocumentSummary]


class DeleteResponse(BaseModel):
    document_id: str
    deleted_chunks: int
    deleted: bool


# --------------------------------------------------------------------------- #
# Query
# --------------------------------------------------------------------------- #
class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    namespace: str = Field(default="default", max_length=128)
    top_k: Optional[int] = Field(
        default=None, ge=1, le=50,
        description="Number of chunks to ground the answer on. Defaults to FINAL_TOP_K.",
    )
    answer_style: Literal["concise", "detailed", "bullet"] = "detailed"
    # Per-request overrides for retrieval behaviour (optional).
    hybrid: Optional[bool] = None
    rerank: Optional[bool] = None
    include_chunks: bool = Field(
        default=False,
        description="If true, return the full retrieved chunks with per-signal scores.",
    )


class CitationModel(BaseModel):
    marker: str
    chunk_id: str
    document_id: str
    filename: str
    ordinal: int
    snippet: str
    score: float


class RetrievedChunkModel(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    ordinal: int
    text: str
    score: float
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None
    fused_score: Optional[float] = None
    rerank_score: Optional[float] = None


class QueryResponse(BaseModel):
    answer: str
    grounded: bool
    model: str
    namespace: str
    citations: List[CitationModel]
    timings_ms: Dict[str, float]
    warnings: List[str] = Field(default_factory=list)
    chunks: Optional[List[RetrievedChunkModel]] = None


# --------------------------------------------------------------------------- #
# Admin / analytics
# --------------------------------------------------------------------------- #
class NamespaceStat(BaseModel):
    namespace: str
    documents: int
    chunks: int


class StatsResponse(BaseModel):
    total_documents: int
    total_chunks: int
    total_queries: int
    namespaces: List[NamespaceStat]
    embedding_provider: str
    vector_backend: str
    rerank_provider: str
    llm_model: str
    llm_active: bool


class QueryLogModel(BaseModel):
    id: str
    ts: float
    namespace: str
    question: str
    grounded: bool
    num_citations: int
    latency_ms: float
    model: str
    success: bool


class QueryLogList(BaseModel):
    total: int
    items: List[QueryLogModel]


class MetricsResponse(BaseModel):
    window: str
    total_queries: int
    success_rate: float
    grounded_rate: float
    avg_latency_ms: float
    p95_latency_ms: float
    queries_per_namespace: Dict[str, int]


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str


class ComponentStatus(BaseModel):
    name: str
    ok: bool
    detail: str = ""


class ReadyResponse(BaseModel):
    ready: bool
    components: List[ComponentStatus]


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str
