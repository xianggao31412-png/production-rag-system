"""
Query route.

    POST /v1/query     ask a question against a namespace

Returns a grounded answer with citations, per-stage timings, and (optionally)
the full retrieved chunks with their per-signal scores for inspection.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_container, require_api_key
from app.container import Container
from app.models.schemas import QueryRequest, QueryResponse

router = APIRouter(prefix="/v1", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query(
    req: QueryRequest,
    _: str = Depends(require_api_key),
    container: Container = Depends(get_container),
) -> QueryResponse:
    return container.query_service.answer(req)
