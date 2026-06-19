"""
Health routes.

    GET /health    liveness  — is the process up? (always cheap, no deps)
    GET /ready     readiness — are the dependencies usable?

Both are unauthenticated and exempt from rate limiting so orchestrators
(Docker, Kubernetes, load balancers) can probe them freely. ``/ready`` reports
each component individually; the network LLM is treated as optional because the
extractive stub guarantees the query path still works without it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_container
from app.container import Container
from app.models.schemas import HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(container: Container = Depends(get_container)) -> HealthResponse:
    s = container.settings
    return HealthResponse(
        status="ok",
        app=s.app_name,
        version=s.app_version,
        environment=s.environment,
    )


@router.get("/ready", response_model=ReadyResponse)
async def ready(
    response: Response,
    container: Container = Depends(get_container),
) -> ReadyResponse:
    components = container.admin_service.readiness()
    all_ok = all(c.ok for c in components)
    if not all_ok:
        response.status_code = 503
    return ReadyResponse(ready=all_ok, components=components)
