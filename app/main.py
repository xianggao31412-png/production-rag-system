"""
Application entry point / factory.

``create_app()`` builds a fully wired FastAPI instance:

* structured logging configured from settings
* a lifespan that constructs the DI container (rebuilding the BM25 index from
  the durable catalogue) on startup and flushes state on shutdown
* consistent JSON error envelopes for domain, validation, and unexpected errors
* request-tracing and rate-limiting middleware, plus CORS
* the ``/v1`` API, health probes, and the operations dashboard

Run with:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api import routes_admin, routes_documents, routes_health, routes_query
from app.config import Settings, get_settings
from app.container import Container
from app.dashboard.router import mount_dashboard
from app.errors import AppError, app_error_handler, unhandled_error_handler
from app.logging_config import configure_logging, get_logger, request_id_ctx
from app.middleware.rate_limit import RateLimitMiddleware, TokenBucketLimiter
from app.middleware.request_id import RequestIDMiddleware

logger = get_logger("eka.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    logger.info("startup_begin", extra={"app": settings.app_name,
                                         "version": settings.app_version,
                                         "environment": settings.environment})
    app.state.container = Container.build(settings)
    logger.info("startup_complete")
    try:
        yield
    finally:
        logger.info("shutdown_begin")
        app.state.container.shutdown()
        logger.info("shutdown_complete")


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Render FastAPI's validation errors in the same envelope as everything else."""
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "detail": _summarise_validation(exc),
            "request_id": request_id_ctx.get(),
        },
    )


def _summarise_validation(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors()[:5]:
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        parts.append(f"{loc}: {err.get('msg', 'invalid')}")
    return "; ".join(parts) or "Request validation failed."


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Enterprise Knowledge Assistant — a hybrid-retrieval RAG platform "
            "with reranking, grounded citations, namespace isolation, and a "
            "built-in operations dashboard."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings

    # ---- Error handlers --------------------------------------------------
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    # ---- Middleware (added inner-first; last added is outermost) ---------
    if settings.rate_limit_enabled:
        limiter = TokenBucketLimiter(
            per_minute=settings.rate_limit_per_minute,
            burst=settings.rate_limit_burst,
        )
        app.add_middleware(
            RateLimitMiddleware,
            limiter=limiter,
            api_key_header=settings.api_key_header,
        )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # ---- Routes ----------------------------------------------------------
    app.include_router(routes_health.router)
    app.include_router(routes_documents.router)
    app.include_router(routes_query.router)
    app.include_router(routes_admin.router)
    mount_dashboard(app)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/dashboard")

    return app


# ASGI entry point for `uvicorn app.main:app`.
app = create_app()
