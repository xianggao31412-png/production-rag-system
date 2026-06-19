"""
Rate-limiting middleware.

A small in-process token-bucket limiter, keyed by API key when present and
falling back to client IP. Each client gets a bucket that refills at
``rate_limit_per_minute`` tokens/minute up to a ceiling of ``rate_limit_burst``;
a request costs one token. When the bucket is empty the request is rejected with
a ``429`` carrying the standard error envelope and a ``Retry-After`` header.

This is intentionally dependency-free (no Redis) so the service runs anywhere
out of the box. For a multi-replica deployment you would swap this for a shared
store, but the interface — one ``allow(key)`` decision per request — stays the
same. Health and dashboard endpoints are exempt so monitoring is never throttled.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.logging_config import get_logger, request_id_ctx

logger = get_logger("eka.ratelimit")

_EXEMPT_PREFIXES = ("/health", "/ready", "/dashboard", "/docs", "/openapi.json", "/redoc")


class TokenBucketLimiter:
    def __init__(self, per_minute: int, burst: int):
        self._rate_per_sec = per_minute / 60.0
        self._capacity = float(burst)
        self._buckets: Dict[str, Tuple[float, float]] = {}  # key -> (tokens, last_ts)
        self._lock = threading.Lock()

    def allow(self, key: str) -> Tuple[bool, float]:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (self._capacity, now))
            tokens = min(self._capacity, tokens + (now - last) * self._rate_per_sec)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True, 0.0
            self._buckets[key] = (tokens, now)
            # Seconds until one token is available.
            retry_after = (1.0 - tokens) / self._rate_per_sec if self._rate_per_sec else 60.0
            return False, retry_after


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter: TokenBucketLimiter, api_key_header: str):
        super().__init__(app)
        self._limiter = limiter
        self._api_key_header = api_key_header

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        key = request.headers.get(self._api_key_header)
        if not key:
            client = request.client
            key = f"ip:{client.host}" if client else "ip:unknown"
        else:
            key = f"key:{key}"

        allowed, retry_after = self._limiter.allow(key)
        if not allowed:
            logger.info("rate_limited", extra={"client": key, "path": path})
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(int(retry_after) + 1)},
                content={
                    "error": "rate_limited",
                    "detail": "Too many requests. Slow down and retry shortly.",
                    "request_id": request_id_ctx.get(),
                },
            )
        return await call_next(request)
