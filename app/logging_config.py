"""
Structured logging.

Emits one JSON object per log line so logs are machine-parseable by any log
aggregator (Loki, Elastic, CloudWatch, ...). A `request_id` is attached to every
record automatically via a context variable, which the request-id middleware
sets at the start of each request. This is how a single user request can be
traced across ingestion, retrieval, and generation.
"""
from __future__ import annotations

import contextvars
import datetime as dt
import json
import logging
import sys
from typing import Any, Dict

# Set per-request by the RequestIdMiddleware; read by the log formatter.
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

# Standard LogRecord attributes we never want to duplicate inside "extra".
_RESERVED = set(
    logging.makeLogRecord({}).__dict__.keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": dt.datetime.fromtimestamp(
                record.created, tz=dt.timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        # Merge any structured fields passed via logger.info(..., extra={...}).
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class PlainFormatter(logging.Formatter):
    """Human-friendly formatter for local development."""

    def format(self, record: logging.LogRecord) -> str:
        rid = request_id_ctx.get()
        base = (
            f"{self.formatTime(record, '%H:%M:%S')} "
            f"{record.levelname:<7} [{rid}] {record.name}: {record.getMessage()}"
        )
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    """Install a single stdout handler with the chosen formatter."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Remove pre-existing handlers so reconfiguration (tests, reload) is clean.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_logs else PlainFormatter())
    root.addHandler(handler)

    # Tame noisy third-party loggers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


class _SafeLoggerAdapter(logging.LoggerAdapter):
    """Logger wrapper that prevents ``extra`` from clobbering reserved fields.

    Python raises ``KeyError`` if ``logger.info(..., extra={...})`` contains a
    key that collides with a built-in ``LogRecord`` attribute (``filename``,
    ``module``, ``name``, ...). Rather than make every call site memorise that
    list, any colliding key is transparently re-homed under an ``x_`` prefix.
    """

    def process(self, msg, kwargs):
        extra = kwargs.get("extra")
        if extra:
            safe = {}
            for key, value in extra.items():
                if key in _RESERVED or key.startswith("_"):
                    safe[f"x_{key}"] = value
                else:
                    safe[key] = value
            kwargs["extra"] = safe
        return msg, kwargs


def get_logger(name: str) -> logging.LoggerAdapter:
    return _SafeLoggerAdapter(logging.getLogger(name), {})
