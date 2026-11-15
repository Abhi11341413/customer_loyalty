"""Enums: segments, objectives, draft states, severities, reason codes.

Owner: SHARED — all owners must approve changes (CLAUDE.md §12.1).

This first version adds the enums the policy engine (M2) needs. M1/M3/M4 add
their own enums (draft states, severities, ...) in follow-up PRs.
"""

from enum import StrEnum


class Segment(StrEnum):
    """Classification labels (§5.1). Engagement axis + loyalty qualifier + billing flag."""

    # Engagement axis (exactly one)
    CONSISTENT = "CONSISTENT"
    DECLINING_ACTIVITY = "DECLINING_ACTIVITY"
    DORMANT = "DORMANT"
    STANDARD = "STANDARD"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    # Qualifier / flag (optional)
    LOYALTY_CANDIDATE = "LOYALTY_CANDIDATE"
    PAYMENT_REMINDER = "PAYMENT_REMINDER"


class BillState(StrEnum):
    """Derived bill state (§6.2)."""

    PAID = "PAID"
    NOT_YET_DUE = "NOT_YET_DUE"
    OVERDUE = "OVERDUE"
    PARTIALLY_PAID_OVERDUE = "PARTIALLY_PAID_OVERDUE"
    DISPUTED = "DISPUTED"
    DATA_CONFLICT = "DATA_CONFLICT"
    NO_BILL = "NO_BILL"


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
