"""
Error types and handlers.

Domain code raises the small set of exceptions defined here. The FastAPI
handlers translate them into consistent JSON error envelopes that always carry
the request id, so a client (or the dashboard) can quote a single id when
reporting a problem.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.logging_config import get_logger, request_id_ctx

logger = get_logger("eka.errors")


class AppError(Exception):
    """Base class for expected, client-facing errors."""
    status_code = 400
    error_code = "app_error"

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFoundError(AppError):
    status_code = 404
    error_code = "not_found"


class ValidationError(AppError):
    status_code = 422
    error_code = "validation_error"


class UnsupportedFileTypeError(AppError):
    status_code = 415
    error_code = "unsupported_file_type"


class EmptyDocumentError(AppError):
    status_code = 422
    error_code = "empty_document"


class AuthError(AppError):
    status_code = 401
    error_code = "unauthorized"


class RateLimitError(AppError):
    status_code = 429
    error_code = "rate_limited"


class UpstreamError(AppError):
    """A dependency (LLM, embedding service, vector DB) failed."""
    status_code = 502
    error_code = "upstream_error"


def _envelope(error_code: str, detail: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error_code,
            "detail": detail,
            "request_id": request_id_ctx.get(),
        },
    )


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error("app_error", extra={"error_code": exc.error_code, "detail": exc.detail})
    else:
        logger.info("app_error", extra={"error_code": exc.error_code, "detail": exc.detail})
    return _envelope(exc.error_code, exc.detail, exc.status_code)


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception")
    return _envelope("internal_error", "An unexpected error occurred.", 500)
