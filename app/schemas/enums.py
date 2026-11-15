"""Enums shared across modules: segments, bill states, confidence bands, account status.

Owner: SHARED — changes need approval from all affected owners.
Other members add their enums (objectives, draft states, severities, ...) here in small PRs.
"""

from enum import StrEnum


class EngagementSegment(StrEnum):
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
