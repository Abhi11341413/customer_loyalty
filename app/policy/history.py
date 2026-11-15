"""Helpers over communication history shared by billing, offers and contact rules.

Owner: M2.
"""

from collections.abc import Iterable
from datetime import date

from app.schemas.customer import CommunicationRecord

BILLING_REMINDER_GROUP = "BILLING_REMINDER"


def objective_group(objective: str) -> str:
    """All billing-reminder stages count as one objective for duplicate checks."""
    return BILLING_REMINDER_GROUP if objective.startswith(BILLING_REMINDER_GROUP) else objective


def history_as_of(history: Iterable[CommunicationRecord], as_of: date) -> list[CommunicationRecord]:
    """Leakage guard: ignore anything sent after ``as_of``."""
    return [h for h in history if h.sent_at.date() <= as_of]


def days_since(record: CommunicationRecord, as_of: date) -> int:
    return (as_of - record.sent_at.date()).days
