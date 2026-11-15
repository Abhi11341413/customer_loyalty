"""BillingDecision, OfferDecision, ContactDecision, StrategyDecision.

Owner: SHARED — all owners must approve changes (CLAUDE.md §12.1).

Two groups of models live here:

1. **Input records** the policy engine reads (bills, payments, communication history,
   contact preferences, campaigns, offers, redemptions). They mirror the tables in §4.4.
   M1's ``CustomerProfile`` should reuse these classes rather than redefine them.
2. **Decision outputs** produced by ``app/policy/`` (§6, §7). They are frozen so no
   downstream component can mutate a policy decision.

Money is always integer minor units (paise) — D11.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import (
    AccountStatus,
    BillState,
    MessageCategory,
    Objective,
    OfferType,
    OfferValueType,
    Segment,
)

_RECORD = ConfigDict(extra="forbid", frozen=True)
_DECISION = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- inputs


class BillingRecord(BaseModel):
    """One bill (T6). ``due_date``/``amount_due_minor`` may be missing in bad data."""

    model_config = _RECORD

    bill_id: str
    customer_id: str
    billing_period: str = Field(pattern=r"^\d{4}-\d{2}$")
    issue_date: date
    due_date: date | None = None
    amount_due_minor: int | None = None
    currency: str = "INR"
    status: Literal["PAID", "UNPAID", "PARTIALLY_PAID", "WAIVED"]
    dispute_status: Literal["NONE", "OPEN", "RESOLVED"] = "NONE"


class Payment(BaseModel):
    """One (possibly partial) payment against a bill (T7)."""

    model_config = _RECORD

    payment_id: str
    bill_id: str
    paid_date: date
    amount_paid_minor: int = Field(gt=0)


class CommRecord(BaseModel):
    """Metadata of a past message (T8). Never contains the body."""

    model_config = _RECORD

    comm_id: str
    customer_id: str
    sent_at: datetime
    channel: str = "EMAIL"
    category: MessageCategory
    objective: str
    reminder_stage: int | None = Field(default=None, ge=1, le=3)
    related_bill_id: str | None = None
    offer_id: str | None = None
    draft_id: str | None = None
    source: Literal["HISTORICAL_SEED", "MOCK_DELIVERY"] = "HISTORICAL_SEED"


class ContactPreferences(BaseModel):
    """Consent and communication preferences (T2)."""

    model_config = _RECORD

    customer_id: str
    email_service_consent: bool
    email_marketing_consent: bool
    email_opt_out: bool = False
    preferred_channel: Literal["EMAIL", "SMS", "NONE"] = "EMAIL"
    do_not_contact_until: date | None = None


class Campaign(BaseModel):
    """Marketing campaign (T9)."""

    model_config = _RECORD

    campaign_id: str
    name: str
    status: Literal["DRAFT", "APPROVED", "ACTIVE", "PAUSED", "ENDED"]
    start_date: date
    end_date: date


class CampaignOffer(BaseModel):
    """Approved offer (T10).

    Deliberately permissive on ``value``/``title``/``terms_summary`` so that incomplete
    rows reach the eligibility engine and are rejected with ``OFFER_TERMS_INCOMPLETE``
    instead of crashing the loader.
    """

    model_config = _RECORD

    offer_id: str
    campaign_id: str
    offer_type: OfferType
    title: str
    value_type: OfferValueType
    value: int
    terms_summary: str
    valid_from: date
    valid_to: date
    channel: Literal["EMAIL", "SMS", "ANY"]
    eligible_segments: list[Segment]
    min_tenure_months: int = 0
    requires_no_overdue: bool = True
    max_per_customer: int = 1
    total_cap: int | None = None
    total_redeemed: int = 0


class OfferRedemption(BaseModel):
    """A customer redeemed an offer (T12)."""

    model_config = _RECORD

    redemption_id: str
    offer_id: str
    customer_id: str
    redeemed_at: datetime


class OfferCustomerContext(BaseModel):
    """The minimal customer facts offer eligibility needs (built from M1's features)."""

    model_config = _RECORD

    customer_id: str
    segments: frozenset[Segment]
    tenure_months: int = Field(ge=0)
    active_plan_ids: frozenset[str] = frozenset()
    account_status: AccountStatus
    bill_state: BillState


# --------------------------------------------------------------------------- decisions


class BillingDecision(BaseModel):
    """Output of the BillingPolicyEngine (§6.3)."""

    model_config = _DECISION

    state: BillState
    reminder_allowed: bool
    escalate: bool = False
    stage: int | None = None
    bill_id: str | None = None
    days_overdue: int | None = None
    outstanding_minor: int | None = None
    #: The ONLY billing facts the LLM may reference (slot name -> display value).
    verified_facts: dict[str, str] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)


class VerifiedOffer(BaseModel):
    """An offer that passed every eligibility check, with pre-formatted display values."""

    model_config = _DECISION

    offer_id: str
    offer_type: OfferType
    title: str
    value_display: str
    terms_summary: str
    valid_to_display: str


class OfferEvaluation(BaseModel):
    model_config = _DECISION

    offer_id: str
    eligible: bool
    failed_checks: list[str] = Field(default_factory=list)
    offer: VerifiedOffer | None = None


class OfferDecision(BaseModel):
    """All evaluated offers. Selection of one offer is done by the StrategySelector."""

    model_config = _DECISION

    eligible: list[OfferEvaluation] = Field(default_factory=list)
    rejected: list[OfferEvaluation] = Field(default_factory=list)
    selected_offer_id: str | None = None


class ContactDecision(BaseModel):
    """Output of the ContactPolicyGate (§6.5)."""

    model_config = _DECISION

    allowed: bool
    category: MessageCategory
    reasons: list[str] = Field(default_factory=list)


class SuppressedObjective(BaseModel):
    """An objective that applied but lost to a higher-precedence one (shown in the UI)."""

    model_config = _DECISION

    objective: Objective
    reason_codes: list[str] = Field(default_factory=list)


class StrategyDecision(BaseModel):
    """Output of the StrategySelector (§7.3)."""

    model_config = _DECISION

    objective: Objective
    category: MessageCategory | None = None
    template_id: str | None = None
    template_version: str | None = None
    tone: str | None = None
    allowed_offer: VerifiedOffer | None = None
    required_disclaimer_keys: list[str] = Field(default_factory=list)
    cta_key: str | None = None
    reminder_stage: int | None = None
    suppressed: list[SuppressedObjective] = Field(default_factory=list)
    rationale_codes: list[str] = Field(default_factory=list)
