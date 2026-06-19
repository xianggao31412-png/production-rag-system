"""
Admin / analytics routes (consumed by the dashboard).

    GET /v1/admin/stats      catalogue + configuration snapshot
    GET /v1/admin/metrics    operational metrics over a recent window
    GET /v1/admin/queries    recent query feed
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_container, require_api_key
from app.container import Container
from app.models.schemas import MetricsResponse, QueryLogList, StatsResponse

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/stats", response_model=StatsResponse)
async def stats(
    _: str = Depends(require_api_key),
    container: Container = Depends(get_container),
) -> StatsResponse:
    return container.admin_service.stats()


@router.get("/metrics", response_model=MetricsResponse)
async def metrics(
    _: str = Depends(require_api_key),
    container: Container = Depends(get_container),
) -> MetricsResponse:
    return container.admin_service.metrics()


@router.get("/queries", response_model=QueryLogList)
async def recent_queries(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: str = Depends(require_api_key),
    container: Container = Depends(get_container),
) -> QueryLogList:
    return container.admin_service.recent_queries(limit=limit, offset=offset)
