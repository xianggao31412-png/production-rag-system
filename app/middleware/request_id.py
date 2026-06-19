"""
Request-ID middleware.

Assigns a unique id to every request (honouring an inbound ``X-Request-ID`` if
the caller supplied one), stores it in a ContextVar so every log line emitted
while handling the request carries it, and echoes it back on the response. This
is what lets you grep one id across the JSON logs and tie together everything
that happened for a single call — the backbone of request tracing.
"""
from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.logging_config import get_logger, request_id_ctx

logger = get_logger("eka.access")

_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get(_HEADER) or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers[_HEADER] = rid
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": round(elapsed_ms, 2),
                "request_id": rid,
            },
        )
        return response
