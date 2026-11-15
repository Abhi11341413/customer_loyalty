"""StrategySelector: objective map, conflict resolution, fallbacks (§7, §16 demo scenarios)."""

import pytest

from app.policy import strategy as s
from app.policy.config import load_strategy_config
from app.policy.offers import decide_offers
from app.policy.strategy import apply_contact, select_strategy
from app.schemas.enums import AccountStatus, BillState, MessageCategory, Objective, Segment
from app.schemas.policy import (
    BillingDecision,
    ContactDecision,
    OfferCustomerContext,
    OfferDecision,
)
from tests.unit.policy.policy_factories import AS_OF, offer

CFG = load_strategy_config()
C, L, P = Segment.CONSISTENT, Segment.LOYALTY_CANDIDATE, Segment.PAYMENT_REMINDER
DEC, DOR, STD, INS = (
    Segment.DECLINING_ACTIVITY,
    Segment.DORMANT,
    Segment.STANDARD,
    Segment.INSUFFICIENT_DATA,
)

PAID = BillingDecision(state=BillState.PAID, reminder_allowed=False)
NO_OFFERS = OfferDecision()


def overdue(stage=1, allowed=True, **kw):
    return BillingDecision(
        state=BillState.OVERDUE,
        reminder_allowed=allowed,
        stage=stage if allowed else None,
        verified_facts={"bill_period": "October 2026", "days_overdue": "5"} if allowed else {},
        reason_codes=["BILL_OVERDUE_DAYS:5"],
        **kw,
    )


def escalated(code):
    return BillingDecision(
        state=BillState.DISPUTED, reminder_allowed=False, escalate=True, reason_codes=[code]
    )


def offers_of(*catalogue, segments):
    """Run the real offer engine so strategy tests use realistic OfferDecisions."""
    from tests.unit.policy.policy_factories import campaign

    ctx = OfferCustomerContext(
        customer_id="C0002",
        segments=frozenset(segments),
        tenure_months=31,
        active_plan_ids=frozenset({"PL-POST-499"}),
        account_status=AccountStatus.ACTIVE,
        bill_state=BillState.PAID,
    )
    camps = [campaign(), campaign(campaign_id="CMP-RE")]
    return decide_offers(ctx, list(catalogue), camps, as_of=AS_OF)


LOY = offer()
RE5 = offer(
    offer_id="OFF-RE-5GB",
    campaign_id="CMP-RE",
    offer_type="REENGAGEMENT",
    title="5 GB bonus data",
    value_type="BONUS_DATA_GB",
    value=5,
    min_tenure_months=0,
    eligible_segments=[DEC, DOR],
    terms_summary="5 GB added for 30 days.",
)
PERK = offer(
    offer_id="OFF-PERK-100",
    offer_type="APPRECIATION_PERK",
    eligible_segments=[C],
    min_tenure_months=0,
    value_type="POINTS",
    value=100,
    title="Thank-you points",
)


# --------------------------------------------------------------------------- demo scenarios


def test_c0001_consistent_appreciation_without_offer():
    d = select_strategy({C}, PAID, NO_OFFERS, CFG)
    assert d.objective is Objective.APPRECIATION
    assert d.category is MessageCategory.MARKETING
    assert d.template_id == "appreciation_v1" and d.template_version == "1.0"
    assert d.allowed_offer is None
    assert d.required_disclaimer_keys == ["unsubscribe"]


def test_consistent_gets_appreciation_perk_if_eligible():
    d = select_strategy({C}, PAID, offers_of(PERK, segments={C}), CFG)
    assert d.objective is Objective.APPRECIATION
    assert d.allowed_offer.offer_id == "OFF-PERK-100"
    assert d.required_disclaimer_keys == ["unsubscribe", "offer_terms"]


def test_c0002_loyalty_reward_with_exactly_one_offer():
    d = select_strategy({C, L}, PAID, offers_of(LOY, segments={C, L}), CFG)
    assert d.objective is Objective.LOYALTY_REWARD
    assert d.allowed_offer.offer_id == "OFF-LOY-200"
    assert d.template_id == "loyalty_reward_v1" and d.tone == "warm_celebratory"
    assert d.required_disclaimer_keys == ["unsubscribe", "offer_terms"]
    assert d.cta_key == "view_reward"


def test_loyalty_without_eligible_offer_falls_back_to_appreciation():
    d = select_strategy({C, L}, PAID, NO_OFFERS, CFG)
    assert d.objective is Objective.APPRECIATION and d.allowed_offer is None
    assert d.suppressed[0].objective is Objective.LOYALTY_REWARD
    assert d.suppressed[0].reason_codes == [s.STRATEGY_NO_ELIGIBLE_OFFER]


def test_loyalty_never_uses_reengagement_offer():
    d = select_strategy({C, L}, PAID, offers_of(RE5, segments={C, L, DEC}), CFG)
    assert d.objective is Objective.APPRECIATION and d.allowed_offer is None


def test_c0003_declining_reengagement_with_offer():
    d = select_strategy({DEC}, PAID, offers_of(RE5, segments={DEC}), CFG)
    assert d.objective is Objective.REENGAGEMENT
    assert d.template_id == "reengagement_declining_v1"
    assert d.allowed_offer.offer_id == "OFF-RE-5GB"


def test_declining_without_offer_still_reengages():
    d = select_strategy({DEC}, PAID, NO_OFFERS, CFG)
    assert d.objective is Objective.REENGAGEMENT and d.allowed_offer is None
    assert d.required_disclaimer_keys == ["unsubscribe"]


def test_c0004_dormant_winback():
    d = select_strategy({DOR}, PAID, offers_of(RE5, segments={DOR}), CFG)
    assert d.objective is Objective.WINBACK and d.template_id == "winback_dormant_v1"
    assert d.allowed_offer.offer_id == "OFF-RE-5GB"


@pytest.mark.parametrize(
    ("stage", "objective", "template"),
    [
        (1, Objective.BILLING_REMINDER_COURTEOUS, "billing_reminder_stage1"),
        (2, Objective.BILLING_REMINDER_FOLLOWUP, "billing_reminder_stage2"),
        (3, Objective.BILLING_REMINDER_FIRM, "billing_reminder_stage3"),
    ],
)
def test_c0005_c0006_billing_stage_objectives(stage, objective, template):
    d = select_strategy({C, P}, overdue(stage), NO_OFFERS, CFG)
    assert d.objective is objective and d.template_id == template
    assert d.category is MessageCategory.SERVICE
    assert d.reminder_stage == stage
    assert d.allowed_offer is None
    assert d.required_disclaimer_keys == ["already_paid", "support_dispute_path"]


def test_c0009_loyal_and_overdue_gets_reminder_only():
    offers = offers_of(LOY, segments={C, L})  # even if an offer slipped through, it is not used
    d = select_strategy({C, L, P}, overdue(2), offers, CFG)
    assert d.objective is Objective.BILLING_REMINDER_FOLLOWUP
    assert d.allowed_offer is None
    assert d.suppressed[0].objective is Objective.LOYALTY_REWARD
    assert d.suppressed[0].reason_codes == [s.STRATEGY_BILLING_PRIORITY]


def test_declining_and_overdue_gets_reminder_only():
    d = select_strategy({DEC, P}, overdue(1), NO_OFFERS, CFG)
    assert d.objective is Objective.BILLING_REMINDER_COURTEOUS
    assert d.suppressed[0].objective is Objective.REENGAGEMENT


@pytest.mark.parametrize("code", ["BILL_DISPUTED", "BILL_DATA_CONFLICT:OVERPAYMENT"])
def test_c0010_dispute_or_conflict_escalates(code):
    d = select_strategy({C, L}, escalated(code), NO_OFFERS, CFG)
    assert d.objective is Objective.ESCALATE
    assert d.category is None and d.template_id is None
    assert d.rationale_codes == [s.STRATEGY_BILLING_ESCALATION, code]


def test_insufficient_data_escalates():
    d = select_strategy({INS}, PAID, NO_OFFERS, CFG)
    assert d.objective is Objective.ESCALATE
    assert d.rationale_codes == [s.STRATEGY_SEGMENT_ESCALATION, "INSUFFICIENT_DATA"]


def test_standard_customer_gets_no_contact():
    d = select_strategy({STD}, PAID, NO_OFFERS, CFG)
    assert d.objective is Objective.NO_CONTACT and d.rationale_codes == [
        s.STRATEGY_NO_TARGET_PATTERN
    ]


def test_overdue_but_reminder_too_recent_means_no_contact_not_marketing():
    billing = overdue(allowed=False)
    d = select_strategy({C, L, P}, billing, NO_OFFERS, CFG)
    assert d.objective is Objective.NO_CONTACT
    assert s.STRATEGY_REMINDER_NOT_ALLOWED in d.rationale_codes
    assert d.suppressed[0].objective is Objective.LOYALTY_REWARD


def test_dormant_outranks_declining():
    assert select_strategy({DOR, DEC}, PAID, NO_OFFERS, CFG).objective is Objective.WINBACK


# --------------------------------------------------------------------------- contact


def refused(*reasons, category=MessageCategory.MARKETING):
    return ContactDecision(allowed=False, category=category, reasons=list(reasons))


def test_c0007_opted_out_becomes_no_contact_by_policy():
    plan = select_strategy({C, L}, PAID, offers_of(LOY, segments={C, L}), CFG)
    d = apply_contact(plan, refused("CONTACT_EMAIL_OPT_OUT", "CONTACT_NO_MARKETING_CONSENT"))
    assert d.objective is Objective.NO_CONTACT_BY_POLICY
    assert d.allowed_offer is None and d.template_id is None
    assert d.rationale_codes == [
        s.STRATEGY_CONTACT_REFUSED,
        "CONTACT_EMAIL_OPT_OUT",
        "CONTACT_NO_MARKETING_CONSENT",
    ]
    assert d.suppressed[0].objective is Objective.LOYALTY_REWARD


def test_overdue_without_service_consent_is_refused():
    plan = select_strategy({P}, overdue(1), NO_OFFERS, CFG)
    d = apply_contact(plan, refused("CONTACT_NO_SERVICE_CONSENT", category=MessageCategory.SERVICE))
    assert d.objective is Objective.NO_CONTACT_BY_POLICY


def test_allowed_contact_keeps_plan():
    plan = select_strategy({C}, PAID, NO_OFFERS, CFG)
    ok = ContactDecision(allowed=True, category=MessageCategory.MARKETING)
    assert apply_contact(plan, ok) == plan


def test_escalation_is_not_overridden_by_contact():
    plan = select_strategy({C}, escalated("BILL_DISPUTED"), NO_OFFERS, CFG)
    assert apply_contact(plan, refused("CONTACT_EMAIL_OPT_OUT")).objective is Objective.ESCALATE
