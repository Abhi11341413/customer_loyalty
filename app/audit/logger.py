"""AuditLogger: append-only; no names, emails, bodies or raw prompts.

Owner: M4 (every member emits events through it).
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import literal_column, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow_iso
from app.core.logging import get_correlation_id
from app.data.models import AuditEventRow
from app.schemas.api import AuditEventView
from app.schemas.enums import AuditEventType

logger = logging.getLogger(__name__)

#: Payload keys that must never be stored (FR-09 "without exposing unnecessary personal data").
FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "first_name",
        "name",
        "email",
        "recipient",
        "subject",
        "body",
        "prompt",
        "raw_prompt",
        "system_prompt",
        "user_prompt",
        "response",
        "completion",
        "llm_input",
        "allowed_slots",
    }
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_REDACTED = "[REDACTED]"
MAX_QUERY_LIMIT = 200


def sanitize_payload(payload: Any) -> tuple[Any, int]:
    """Drop forbidden keys and mask email-like strings, recursively.

    Returns the cleaned payload and the number of redactions made.
    """
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        count = 0
        for key, value in payload.items():
            if str(key).lower() in FORBIDDEN_PAYLOAD_KEYS:
                count += 1
                continue
            cleaned[key], sub = sanitize_payload(value)
            count += sub
        return cleaned, count
    if isinstance(payload, list | tuple):
        items = [sanitize_payload(v) for v in payload]
        return [v for v, _ in items], sum(c for _, c in items)
    if isinstance(payload, str) and _EMAIL_RE.search(payload):
        return _EMAIL_RE.sub(_REDACTED, payload), 1
    return payload, 0


class AuditLogger:
    """Append-only audit sink. Exposes only `log` and `query` — no update or delete."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def log(
        self,
        event_type: AuditEventType,
        *,
        customer_ref: str,
        actor: str = "system",
        draft_id: str | None = None,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> str:
        """Record one event and return its id."""
        cleaned, redactions = sanitize_payload(payload or {})
        if redactions:
            cleaned["_redactions"] = redactions
            logger.warning("audit payload redacted", extra={"event_type": str(event_type)})
        row = AuditEventRow(
            event_id=uuid.uuid4().hex,
            ts=utcnow_iso(),
            event_type=str(event_type),
            actor=actor,
            customer_ref=customer_ref,
            draft_id=draft_id,
            payload=cleaned,
            correlation_id=correlation_id or get_correlation_id(),
        )
        with self._sessions.begin() as session:
            session.add(row)
        logger.info("audit", extra={"event_type": str(event_type), "draft_id": draft_id})
        return row.event_id

    def query(
        self,
        *,
        customer_id: str | None = None,
        draft_id: str | None = None,
        correlation_id: str | None = None,
        limit: int = 50,
    ) -> list[AuditEventView]:
        """Most recent `limit` matching events, returned oldest-first (timeline order)."""
        limit = max(1, min(limit, MAX_QUERY_LIMIT))
        stmt = select(AuditEventRow)
        if customer_id:
            stmt = stmt.where(AuditEventRow.customer_ref == customer_id)
        if draft_id:
            stmt = stmt.where(AuditEventRow.draft_id == draft_id)
        if correlation_id:
            stmt = stmt.where(AuditEventRow.correlation_id == correlation_id)
        # rowid breaks ties between events written within the same clock tick.
        stmt = stmt.order_by(
            AuditEventRow.ts.desc(), literal_column("audit_events.rowid").desc()
        ).limit(limit)
        with self._sessions() as session:
            rows = list(session.scalars(stmt))
        rows.reverse()
        return [
            AuditEventView(
                event_id=r.event_id,
                ts=r.ts,
                event_type=r.event_type,
                actor=r.actor,
                customer_ref=r.customer_ref,
                draft_id=r.draft_id,
                payload=r.payload,
                correlation_id=r.correlation_id,
            )
            for r in rows
        ]
