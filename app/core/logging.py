"""JSON logging and correlation-id middleware. Never log secrets or PII.

Owner: M4.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_HEADER = "X-Correlation-ID"
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Extra attributes callers may attach via `extra=`; anything else is dropped so that
# accidental PII in log calls does not reach the output.
_ALLOWED_EXTRA = {
    "error_code",
    "status",
    "method",
    "path",
    "duration_ms",
    "event_type",
    "draft_id",
    "state",
}


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def get_correlation_id() -> str:
    """Current request's correlation id; a fresh one outside a request (scripts/tests)."""
    value = _correlation_id.get()
    if value is None:
        value = new_correlation_id()
        _correlation_id.set(value)
    return value


def set_correlation_id(value: str | None) -> None:
    _correlation_id.set(value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": _correlation_id.get(),
        }
        for key in _ALLOWED_EXTRA:
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on the root logger (idempotent)."""
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)


_ID_SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Assigns a correlation id per request (or accepts a safe incoming one) and logs timing."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(CORRELATION_HEADER, "")
        valid = 0 < len(incoming) <= 64 and set(incoming) <= _ID_SAFE
        correlation_id = incoming if valid else new_correlation_id()
        token = _correlation_id.set(correlation_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            logging.getLogger("app.request").info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            _correlation_id.reset(token)
        response.headers[CORRELATION_HEADER] = correlation_id
        return response
