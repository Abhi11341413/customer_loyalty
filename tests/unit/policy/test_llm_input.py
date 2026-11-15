"""LLMInput builder: minimal, verified, no PII (§8.4, §15.2 test_llm_input_minimal)."""

import pytest

from app.policy.billing import decide_billing
from app.policy.config import load_billing_config, load_strategy_config
from app.policy.llm_input import NotDraftableError, build_llm_input
from app.policy.strategy import select_strategy
from app.schemas.enums import BillState, Objective, OfferType, Segment
from app.schemas.policy import (
    BillingDecision,
    OfferDecision,
    OfferEvaluation,
    StrategyDecision,
    VerifiedOffer,
)
from tests.unit.policy.policy_factories import AS_OF, bill, payment

S_CFG = load_strategy_config()
B_CFG = load_billing_config()
PAID = BillingDecision(state=BillState.PAID, reminder_allowed=False)


def c0005_input():
    billing = decide_billing([bill()], [], [], B_CFG, AS_OF)
    strategy = select_strategy(
        {Segment.CONSISTENT, Segment.PAYMENT_REMINDER}, billing, OfferDecision(), S_CFG
    )
    return build_llm_input(strategy, first_name="Ravi", billing=billing, cfg=S_CFG), billing


def test_billing_reminder_input_matches_blueprint_example():
    inp, _ = c0005_input()
    assert inp.objective is Objective.BILLING_REMINDER_COURTEOUS
    assert inp.segment_summary == "Bill for October 2026 overdue by 5 days"
    assert inp.tone.name == "courteous"
    assert inp.allowed_slots["amount_due"] == "₹599.00"
    assert inp.allowed_slots["due_date"] == "10 Nov 2026"
    assert inp.allowed_slots["bill_period"] == "October 2026"
    assert inp.allowed_slots["pay_cta"] == "View and pay your bill"
    assert inp.allowed_slots["support_path"] == B_CFG.support_path
    assert inp.allowed_slots["first_name"] == "Ravi"
    assert inp.offer is None
    assert inp.required_disclaimers == ["already_paid", "support_dispute_path"]
    assert "legal action" in inp.forbidden


def test_llm_input_contains_no_customer_identifiers():
    inp, billing = c0005_input()
    dumped = inp.model_dump_json()
    assert "C0005" not in dumped and "@" not in dumped
    assert billing.bill_id not in dumped  # internal ids stay out of the prompt
    assert set(inp.model_dump()) == {
        "first_name",
        "objective",
        "segment_summary",
        "tone",
        "allowed_slots",
        "offer",
        "required_disclaimers",
        "template_skeleton",
        "forbidden",
    }


def test_offer_slots_and_plan_name():
    verified = VerifiedOffer(
        offer_id="OFF-LOY-200",
        offer_type=OfferType.LOYALTY_REWARD,
        title="Loyalty credit",
        value_display="₹200 bill credit",
        terms_summary="One-time credit.",
        valid_to_display="31 Dec 2026",
    )
    offers = OfferDecision(
        eligible=[OfferEvaluation(offer_id="OFF-LOY-200", eligible=True, offer=verified)]
    )
    strategy = select_strategy({Segment.CONSISTENT, Segment.LOYALTY_CANDIDATE}, PAID, offers, S_CFG)
    inp = build_llm_input(
        strategy,
        first_name="Asha",
        billing=PAID,
        cfg=S_CFG,
        plan_name="Postpaid 499",
        tone_rules=["max 140 words"],
    )
    assert inp.offer == verified
    assert inp.allowed_slots["offer_value"] == "₹200 bill credit"
    assert inp.allowed_slots["offer_valid_to"] == "31 Dec 2026"
    assert inp.allowed_slots["offer_title"] == "Loyalty credit"
    assert inp.allowed_slots["plan_name"] == "Postpaid 499"
    assert inp.allowed_slots["cta"] == "View your reward"
    assert inp.tone.rules == ["max 140 words"]
    assert "amount_due" not in inp.allowed_slots  # no billing facts in a marketing email


@pytest.mark.parametrize(
    "objective", [Objective.ESCALATE, Objective.NO_CONTACT, Objective.NO_CONTACT_BY_POLICY]
)
def test_non_draft_objectives_rejected(objective):
    with pytest.raises(NotDraftableError):
        build_llm_input(
            StrategyDecision(objective=objective), first_name="Ravi", billing=None, cfg=S_CFG
        )


def test_billing_reminder_without_verified_facts_rejected():
    plan = select_strategy(
        {Segment.PAYMENT_REMINDER},
        decide_billing([bill()], [], [], B_CFG, AS_OF),
        OfferDecision(),
        S_CFG,
    )
    with pytest.raises(NotDraftableError):
        build_llm_input(plan, first_name="Ravi", billing=PAID, cfg=S_CFG)


def test_blank_first_name_rejected():
    plan = select_strategy({Segment.CONSISTENT}, PAID, OfferDecision(), S_CFG)
    with pytest.raises(NotDraftableError):
        build_llm_input(plan, first_name="  ", billing=PAID, cfg=S_CFG)


def test_partial_payment_amount_is_outstanding():
    billing = decide_billing([bill(status="PARTIALLY_PAID")], [payment(30000)], [], B_CFG, AS_OF)
    plan = select_strategy({Segment.PAYMENT_REMINDER}, billing, OfferDecision(), S_CFG)
    inp = build_llm_input(plan, first_name="Ravi", billing=billing, cfg=S_CFG)
    assert inp.allowed_slots["amount_due"] == "₹299.00"
