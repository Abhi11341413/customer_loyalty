"""OfferEligibilityEngine (FR-05): validate every candidate offer.

Owner: M2. Deterministic, no LLM import (CLAUDE.md §6.4).

Every offer gets an explicit list of failed checks; only offers with none become a
``VerifiedOffer``. This engine never creates or modifies offers, and it does not pick
one — that is the StrategySelector's job.

Input: M1's ``CampaignOffer`` (plan eligibility is carried in ``eligible_plan_ids``;
empty = all plans, T11).
"""

import re
from collections.abc import Iterable
from datetime import date

from app.policy.formatting import format_date, format_money
from app.policy.history import days_since, history_as_of
from app.schemas.campaign import Campaign, CampaignOffer, OfferRedemption
from app.schemas.customer import CommunicationRecord
from app.schemas.enums import AccountStatus, BillState, OfferType, OfferValueType
from app.schemas.policy import OfferCustomerContext, OfferDecision, OfferEvaluation, VerifiedOffer

OFFER_ID_PATTERN = re.compile(r"^OFF-[A-Z0-9-]+$")

#: Bill states during which an offer with ``requires_no_overdue`` is blocked (check #9).
BLOCKING_BILL_STATES = frozenset(
    {
        BillState.OVERDUE,
        BillState.PARTIALLY_PAID_OVERDUE,
        BillState.DISPUTED,
        BillState.DATA_CONFLICT,
    }
)

_OFFER_TYPES = {t.value for t in OfferType}
_VALUE_TYPES = {t.value for t in OfferValueType}

# Fail reason codes (§6.4 table)
OFFER_NOT_FOUND = "OFFER_NOT_FOUND"
OFFER_ID_INVALID = "OFFER_ID_INVALID"
CAMPAIGN_DATA_MISSING = "CAMPAIGN_DATA_MISSING"
CAMPAIGN_NOT_ACTIVE = "CAMPAIGN_NOT_ACTIVE"
OFFER_EXPIRED = "OFFER_EXPIRED"
OFFER_NOT_STARTED = "OFFER_NOT_STARTED"
OFFER_TERMS_INCOMPLETE = "OFFER_TERMS_INCOMPLETE"
OFFER_CHANNEL_MISMATCH = "OFFER_CHANNEL_MISMATCH"
OFFER_SEGMENT_INELIGIBLE = "OFFER_SEGMENT_INELIGIBLE"
OFFER_TENURE_SHORT = "OFFER_TENURE_SHORT"
OFFER_PLAN_MISMATCH = "OFFER_PLAN_MISMATCH"
OFFER_BLOCKED_BY_BILLING = "OFFER_BLOCKED_BY_BILLING"
OFFER_REDEMPTION_LIMIT = "OFFER_REDEMPTION_LIMIT"
OFFER_CAP_REACHED = "OFFER_CAP_REACHED"
OFFER_DUPLICATE_RECENT = "OFFER_DUPLICATE_RECENT"
ACCOUNT_NOT_ACTIVE = "ACCOUNT_NOT_ACTIVE"


def format_offer_value(offer: CampaignOffer) -> str:
    """Pre-formatted, verified value text, e.g. ``"₹200 bill credit"``."""
    if offer.value_type == OfferValueType.PERCENT_DISCOUNT:
        return f"{offer.value}% off"
    if offer.value_type == OfferValueType.FLAT_CREDIT_MINOR:
        return f"{format_money(offer.value, 'INR', drop_zero_paise=True)} bill credit"
    if offer.value_type == OfferValueType.BONUS_DATA_GB:
        return f"{offer.value} GB bonus data"
    if offer.value_type == OfferValueType.POINTS:
        return f"{offer.value} bonus points"
    raise ValueError(f"unknown value_type {offer.value_type!r}")


def _terms_complete(offer: CampaignOffer) -> bool:
    return (
        offer.value > 0
        and bool(offer.title.strip())
        and bool(offer.terms_summary.strip())
        and offer.offer_type in _OFFER_TYPES
        and offer.value_type in _VALUE_TYPES
    )


def _to_verified(offer: CampaignOffer) -> VerifiedOffer:
    return VerifiedOffer(
        offer_id=offer.offer_id,
        offer_type=OfferType(offer.offer_type),
        title=offer.title,
        value_display=format_offer_value(offer),
        terms_summary=offer.terms_summary,
        valid_to_display=format_date(offer.valid_to),
    )


def evaluate_offer(
    offer: CampaignOffer,
    campaign: Campaign | None,
    customer: OfferCustomerContext,
    *,
    redemptions: list[OfferRedemption],
    history: list[CommunicationRecord],
    as_of: date,
    channel: str = "EMAIL",
    duplicate_window_days: int = 30,
) -> OfferEvaluation:
    """Run all 13 checks of §6.4 and collect every failure (no short-circuit)."""
    fails: list[str] = []
    segments = {str(s) for s in customer.segments}
    plans = set(offer.eligible_plan_ids)

    if not OFFER_ID_PATTERN.match(offer.offer_id):
        fails.append(OFFER_ID_INVALID)
    if campaign is None:
        fails.append(CAMPAIGN_DATA_MISSING)
    elif campaign.status != "ACTIVE" or not (campaign.start_date <= as_of <= campaign.end_date):
        fails.append(CAMPAIGN_NOT_ACTIVE)
    if as_of > offer.valid_to:
        fails.append(OFFER_EXPIRED)
    if as_of < offer.valid_from:
        fails.append(OFFER_NOT_STARTED)
    if not _terms_complete(offer):
        fails.append(OFFER_TERMS_INCOMPLETE)
    if offer.channel not in (channel, "ANY"):
        fails.append(OFFER_CHANNEL_MISMATCH)
    if not segments & set(offer.eligible_segments):
        fails.append(OFFER_SEGMENT_INELIGIBLE)
    if customer.tenure_months < offer.min_tenure_months:
        fails.append(OFFER_TENURE_SHORT)
    if plans and not customer.active_plan_ids & plans:
        fails.append(OFFER_PLAN_MISMATCH)
    if offer.requires_no_overdue and customer.bill_state in BLOCKING_BILL_STATES:
        fails.append(OFFER_BLOCKED_BY_BILLING)
    used = sum(
        1
        for r in redemptions
        if r.offer_id == offer.offer_id
        and r.customer_id == customer.customer_id
        and r.redeemed_at.date() <= as_of
    )
    if used >= offer.max_per_customer:
        fails.append(OFFER_REDEMPTION_LIMIT)
    if offer.total_cap is not None and offer.total_redeemed >= offer.total_cap:
        fails.append(OFFER_CAP_REACHED)
    if any(
        h.offer_id == offer.offer_id and days_since(h, as_of) < duplicate_window_days
        for h in history_as_of(history, as_of)
    ):
        fails.append(OFFER_DUPLICATE_RECENT)
    if customer.account_status is not AccountStatus.ACTIVE:
        fails.append(ACCOUNT_NOT_ACTIVE)

    return OfferEvaluation(
        offer_id=offer.offer_id,
        eligible=not fails,
        failed_checks=fails,
        offer=None if fails else _to_verified(offer),
    )


def decide_offers(
    customer: OfferCustomerContext,
    offers: Iterable[CampaignOffer],
    campaigns: Iterable[Campaign],
    *,
    redemptions: Iterable[OfferRedemption] = (),
    history: Iterable[CommunicationRecord] = (),
    as_of: date,
    channel: str = "EMAIL",
    candidate_offer_ids: list[str] | None = None,
    duplicate_window_days: int = 30,
) -> OfferDecision:
    """Evaluate candidate offers (``None`` = every offer in the catalogue)."""
    catalogue = {o.offer_id: o for o in offers}
    campaign_by_id = {c.campaign_id: c for c in campaigns}
    redemptions, history = list(redemptions), list(history)

    if candidate_offer_ids is None:
        ids = sorted(catalogue)
    else:
        ids = list(dict.fromkeys(candidate_offer_ids))
    eligible: list[OfferEvaluation] = []
    rejected: list[OfferEvaluation] = []
    for offer_id in ids:
        offer = catalogue.get(offer_id)
        if offer is None:
            code = OFFER_ID_INVALID if not OFFER_ID_PATTERN.match(offer_id) else OFFER_NOT_FOUND
            rejected.append(
                OfferEvaluation(offer_id=offer_id, eligible=False, failed_checks=[code])
            )
            continue
        result = evaluate_offer(
            offer,
            campaign_by_id.get(offer.campaign_id),
            customer,
            redemptions=redemptions,
            history=history,
            as_of=as_of,
            channel=channel,
            duplicate_window_days=duplicate_window_days,
        )
        (eligible if result.eligible else rejected).append(result)
    return OfferDecision(eligible=eligible, rejected=rejected)
