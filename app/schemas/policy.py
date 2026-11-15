"""BillingDecision, OfferDecision, ContactDecision, StrategyDecision.

Owner: SHARED — all owners must approve changes (CLAUDE.md §12.1). Produced by M2.

Decision outputs of ``app/policy/`` (§6, §7). They are frozen so no downstream
component can mutate a policy decision.

Input records are NOT redefined here — the policy engine reads M1's contracts:
``app.schemas.customer`` (BillingRecord, Payment, CommunicationRecord, ContactPreferences)
and ``app.schemas.campaign`` (Campaign, CampaignOffer, OfferRedemption).
"""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import (
    AccountStatus,
    BillState,
    MessageCategory,
    Objective,
    OfferType,
    Segment,
)

_DECISION = ConfigDict(extra="forbid", frozen=True)


class OfferCustomerContext(BaseModel):
    """The minimal customer facts offer eligibility needs.

    Built by the orchestrator from M1's ``CustomerFeatures`` + ``ClassificationResult``
    and M2's ``BillingDecision`` (the bill state used is the policy engine's, §6.2).
    """

    model_config = _DECISION

    customer_id: str
    segments: frozenset[Segment]
    tenure_months: int = Field(ge=0)
    active_plan_ids: frozenset[str] = frozenset()
    account_status: AccountStatus
    bill_state: BillState


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
