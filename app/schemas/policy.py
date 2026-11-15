"""BillingDecision, OfferDecision, ContactDecision, StrategyDecision.

Owner: SHARED (produced by M2). Drafted by M4 for CP0 from blueprint sections 6.3-6.5 and 7.3;
needs approval. Decisions are frozen so they cannot be mutated downstream.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.enums import BillState, MessageCategory, Objective


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BillingDecision(_Frozen):
    state: BillState
    reminder_allowed: bool
    stage: int | None = None
    bill_id: str | None = None
    escalate: bool = False
    # The ONLY billing facts the LLM may reference (pre-formatted display strings).
    verified_facts: dict[str, str] = {}
    reason_codes: list[str] = []


class VerifiedOffer(_Frozen):
    offer_id: str
    offer_type: str
    title: str
    value_display: str  # pre-formatted, e.g. "Rs 200 bill credit"
    terms_summary: str
    valid_to_display: str  # e.g. "31 Dec 2026"


class OfferCheckRequest(_Frozen):
    customer_id: str
    as_of_date: date
    channel: Literal["EMAIL"] = "EMAIL"
    candidate_offer_ids: list[str] | None = None


class OfferEvaluation(_Frozen):
    offer_id: str
    eligible: bool
    failed_checks: list[str] = []
    offer: VerifiedOffer | None = None


class OfferDecision(_Frozen):
    eligible: list[OfferEvaluation] = []
    rejected: list[OfferEvaluation] = []
    selected_offer_id: str | None = None


class ContactDecision(_Frozen):
    allowed: bool
    category: MessageCategory
    reasons: list[str] = []


class SuppressedObjective(_Frozen):
    objective: Objective
    reason_codes: list[str] = []


class StrategyDecision(_Frozen):
    objective: Objective
    category: MessageCategory | None = None
    template_id: str | None = None
    template_version: str | None = None
    tone: str | None = None
    allowed_offer: VerifiedOffer | None = None
    required_disclaimer_keys: list[str] = []
    cta_key: str | None = None
    suppressed: list[SuppressedObjective] = []
    rationale_codes: list[str] = []
