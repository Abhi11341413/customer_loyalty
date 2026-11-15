"""Enums shared across modules: segments, bill states, confidence bands, account status.

Owner: SHARED. Drafted by M4 for CP0 from the blueprint (sections 5.1, 7.1, 9.3, 9.6, 4.4);
needs approval from all owners before merge.
"""

from __future__ import annotations

Owner: SHARED — changes need approval from all affected owners.
Other members add their enums (objectives, draft states, severities, ...) here in small PRs.
"""

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
    """Engagement axis — exactly one per customer, evaluated in precedence order."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DORMANT = "DORMANT"
    DECLINING_ACTIVITY = "DECLINING_ACTIVITY"
    CONSISTENT = "CONSISTENT"
    STANDARD = "STANDARD"


class Segment(StrEnum):
    """Every label that can appear in ClassificationResult.segments."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DORMANT = "DORMANT"
    DECLINING_ACTIVITY = "DECLINING_ACTIVITY"
    CONSISTENT = "CONSISTENT"
    STANDARD = "STANDARD"
    LOYALTY_CANDIDATE = "LOYALTY_CANDIDATE"  # qualifier, only with CONSISTENT
    PAYMENT_REMINDER = "PAYMENT_REMINDER"  # billing flag, independent of engagement


class BillState(StrEnum):
    """Derived state of the customer's current bill."""

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
class BillConflictType(StrEnum):
    MISSING_FIELD = "MISSING_FIELD"
    STATUS_PAYMENT_MISMATCH = "STATUS_PAYMENT_MISMATCH"
    OVERPAYMENT = "OVERPAYMENT"


class ConfidenceBand(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


# --------------------------------------------------------------------------- policy (M2)


class MessageCategory(StrEnum):
    """Consent category of a message (ASM A-05)."""

    SERVICE = "SERVICE"
    MARKETING = "MARKETING"


class Objective(StrEnum):
    """Communication objective chosen by the StrategySelector (§7.1)."""

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


BILLING_REMINDER_OBJECTIVES: frozenset[Objective] = frozenset(
    {
        Objective.BILLING_REMINDER_COURTEOUS,
        Objective.BILLING_REMINDER_FOLLOWUP,
        Objective.BILLING_REMINDER_FIRM,
    }
)

#: Objectives that never produce a draft (no LLM call).
NON_DRAFT_OBJECTIVES: frozenset[Objective] = frozenset(
    {Objective.NO_CONTACT, Objective.NO_CONTACT_BY_POLICY, Objective.ESCALATE}
)


class OfferType(StrEnum):
    LOYALTY_REWARD = "LOYALTY_REWARD"
    REENGAGEMENT = "REENGAGEMENT"
    APPRECIATION_PERK = "APPRECIATION_PERK"


class OfferValueType(StrEnum):
    PERCENT_DISCOUNT = "PERCENT_DISCOUNT"
    FLAT_CREDIT_MINOR = "FLAT_CREDIT_MINOR"
    BONUS_DATA_GB = "BONUS_DATA_GB"
    POINTS = "POINTS"
