"""Enums shared across modules: segments, bill states, objectives, offers, severities.

Owner: SHARED — all owners must approve changes (CLAUDE.md §12.1).
Members add their enums (draft states, severities, ...) here in small PRs.
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
    """Every label that can appear in ClassificationResult.segments (§5.1)."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DORMANT = "DORMANT"
    DECLINING_ACTIVITY = "DECLINING_ACTIVITY"
    CONSISTENT = "CONSISTENT"
    STANDARD = "STANDARD"
    LOYALTY_CANDIDATE = "LOYALTY_CANDIDATE"  # qualifier, only with CONSISTENT
    PAYMENT_REMINDER = "PAYMENT_REMINDER"  # billing flag, independent of engagement


class BillState(StrEnum):
    """Derived state of the customer's current bill (§6.2)."""

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


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"
