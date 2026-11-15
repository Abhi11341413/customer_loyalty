"""Typed exceptions and their HTTP error mapping.

Owner: M4.

Every error leaves the API as
``{"error": {"code", "message", "details"}, "correlation_id": "..."}``.
Messages must never contain PII.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_correlation_id

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for errors that map to a well-defined HTTP response."""

    status_code: int = 400
    code: str = "BAD_REQUEST"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class CustomerNotFoundError(NotFoundError):
    code = "CUSTOMER_NOT_FOUND"


class DraftNotFoundError(NotFoundError):
    code = "DRAFT_NOT_FOUND"


class InvalidStateError(AppError):
    status_code = 409
    code = "INVALID_STATE"


class HashMismatchError(AppError):
    status_code = 409
    code = "HASH_MISMATCH"


class ValidationBlockedError(AppError):
    status_code = 409
    code = "VALIDATION_BLOCKED"


class WarningsNotAcknowledgedError(AppError):
    status_code = 422
    code = "WARNINGS_NOT_ACKNOWLEDGED"


class DuplicatePendingDraftError(AppError):
    status_code = 409
    code = "DUPLICATE_PENDING_DRAFT"


class NotApprovedError(AppError):
    status_code = 409
    code = "NOT_APPROVED"


class DeliveryBlockedError(AppError):
    status_code = 409
    code = "DELIVERY_BLOCKED"


class ComponentNotReadyError(AppError):
    """A pipeline component owned by another member is not implemented/wired yet."""

    status_code = 503
    code = "COMPONENT_NOT_READY"


def _error_response(status: int, code: str, message: str, details: dict[str, Any]) -> JSONResponse:
    correlation_id = get_correlation_id()
    return JSONResponse(
        status_code=status,
        content={
            "error": {"code": code, "message": message, "details": details},
            "correlation_id": correlation_id,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach handlers that turn exceptions into the standard error JSON."""

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        logger.info("request failed", extra={"error_code": exc.code, "status": exc.status_code})
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Only field locations and messages; never echo submitted values (could contain PII).
        errors = [
            {"loc": [str(p) for p in err.get("loc", [])], "msg": err.get("msg", "")}
            for err in exc.errors()
        ]
        return _error_response(
            422, "REQUEST_INVALID", "Request validation failed.", {"errors": errors}
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error")
        return _error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.", {})
