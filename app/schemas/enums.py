"""Enums: segments, objectives, draft states, severities, reason codes.

Owner: SHARED. Drafted by M4 for CP0 from the blueprint (sections 5.1, 7.1, 9.3, 9.6, 4.4);
needs approval from all owners before merge.
"""

from __future__ import annotations

from enum import StrEnum


class EngagementSegment(StrEnum):
    CONSISTENT = "CONSISTENT"
    DECLINING_ACTIVITY = "DECLINING_ACTIVITY"
    DORMANT = "DORMANT"
    STANDARD = "STANDARD"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class Segment(StrEnum):
    """All labels that may appear in ClassificationResult.segments."""

    CONSISTENT = "CONSISTENT"
    DECLINING_ACTIVITY = "DECLINING_ACTIVITY"
    DORMANT = "DORMANT"
    STANDARD = "STANDARD"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    LOYALTY_CANDIDATE = "LOYALTY_CANDIDATE"
    PAYMENT_REMINDER = "PAYMENT_REMINDER"


class ConfidenceBand(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Objective(StrEnum):
    APPRECIATION = "APPRECIATION"
    LOYALTY_REWARD = "LOYALTY_REWARD"
    REENGAGEMENT = "REENGAGEMENT"
    WINBACK = "WINBACK"
    BILLING_REMINDER_COURTEOUS = "BILLING_REMINDER_COURTEOUS"
    BILLING_REMINDER_FOLLOWUP = "BILLING_REMINDER_FOLLOWUP"
    BILLING_REMINDER_FIRM = "BILLING_REMINDER_FIRM"
    NO_CONTACT = "NO_CONTACT"
    NO_CONTACT_BY_POLICY = "NO_CONTACT_BY_POLICY"
    ESCALATE = "ESCALATE"


#: Objectives for which no draft is generated (no LLM call is made).
NON_DRAFTING_OBJECTIVES = frozenset(
    {Objective.NO_CONTACT, Objective.NO_CONTACT_BY_POLICY, Objective.ESCALATE}
)


class MessageCategory(StrEnum):
    SERVICE = "SERVICE"
    MARKETING = "MARKETING"


class BillState(StrEnum):
    PAID = "PAID"
    NOT_YET_DUE = "NOT_YET_DUE"
    OVERDUE = "OVERDUE"
    PARTIALLY_PAID_OVERDUE = "PARTIALLY_PAID_OVERDUE"
    DISPUTED = "DISPUTED"
    DATA_CONFLICT = "DATA_CONFLICT"
    NO_BILL = "NO_BILL"


class Severity(StrEnum):
    """Validation severity. Precedence: BLOCK > ESCALATE > WARN > PASS."""

    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self.value]


_SEVERITY_RANK = {"PASS": 0, "WARN": 1, "ESCALATE": 2, "BLOCK": 3}


class DraftState(StrEnum):
    GENERATED = "GENERATED"
    PENDING_REVIEW = "PENDING_REVIEW"
    BLOCKED = "BLOCKED"
    ESCALATED = "ESCALATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DELIVERED = "DELIVERED"
    DELIVERY_BLOCKED = "DELIVERY_BLOCKED"
    REFUSED = "REFUSED"


class ReviewerActionType(StrEnum):
    EDIT = "EDIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


class RejectionReason(StrEnum):
    FACTUAL_ERROR = "FACTUAL_ERROR"
    WRONG_TONE = "WRONG_TONE"
    WRONG_STRATEGY = "WRONG_STRATEGY"
    POLICY = "POLICY"
    OTHER = "OTHER"


class DeliveryStatus(StrEnum):
    MOCK_SENT = "MOCK_SENT"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class DraftRequestStatus(StrEnum):
    CREATED = "CREATED"
    REFUSED = "REFUSED"
    ESCALATED = "ESCALATED"


class AuditEventType(StrEnum):
    CLASSIFIED = "CLASSIFIED"
    POLICY_DECIDED = "POLICY_DECIDED"
    DRAFT_GENERATED = "DRAFT_GENERATED"
    LLM_FALLBACK = "LLM_FALLBACK"
    VALIDATED = "VALIDATED"
    EDITED = "EDITED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DELIVERY_BLOCKED = "DELIVERY_BLOCKED"
    DELIVERED = "DELIVERED"
    REFUSED = "REFUSED"
    ESCALATED = "ESCALATED"
