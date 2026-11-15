"""Raw campaign / offer data read from the DB (input to OfferEligibilityEngine).

Owner: SHARED (produced by M1's OfferReader, consumed by M2).
Decision models (OfferEvaluation, OfferDecision, ...) live in app/schemas/policy.py (M2).
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class Campaign(BaseModel):
    model_config = ConfigDict(frozen=True)

    campaign_id: str
    name: str
    status: str
    start_date: date
    end_date: date
    approved_by: str | None = None


class CampaignOffer(BaseModel):
    model_config = ConfigDict(frozen=True)

    offer_id: str
    campaign_id: str
    offer_type: str
    title: str
    value_type: str
    value: int
    terms_summary: str
    valid_from: date
    valid_to: date
    channel: str
    eligible_segments: list[str]
    min_tenure_months: int = 0
    requires_no_overdue: bool = True
    max_per_customer: int = 1
    total_cap: int | None = None
    total_redeemed: int = 0
    eligible_plan_ids: list[str] = []  # empty = all active plans


class OfferRedemption(BaseModel):
    redemption_id: str
    offer_id: str
    customer_id: str
    redeemed_at: datetime
