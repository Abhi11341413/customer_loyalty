"""Audit query endpoint.

Owner: M4. FR-09.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_audit
from app.audit.logger import MAX_QUERY_LIMIT, AuditLogger
from app.schemas.api import AuditEventView

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventView])
def list_audit_events(
    customer_id: str | None = Query(default=None, pattern=r"^C\d{4}$"),
    draft_id: str | None = None,
    correlation_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=MAX_QUERY_LIMIT),
    audit: AuditLogger = Depends(get_audit),
) -> list[AuditEventView]:
    return audit.query(
        customer_id=customer_id, draft_id=draft_id, correlation_id=correlation_id, limit=limit
    )
