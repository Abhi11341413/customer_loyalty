"""M2's integration boundary (CLAUDE.md §12): Classification -> Policy -> Strategy -> LLMInput.

Runs the real M1 classification and the real M2 policy engine on the seeded demo customers
C0001-C0010 and checks the outcomes listed in the blueprint's demo table (§16). This is
checkpoint CP1: the no-LLM pipeline works for all ten demo customers.
"""

from datetime import date

import pytest

from app.policy.llm_input import NotDraftableError
from app.policy.service import PolicyService
from app.schemas.enums import NON_DRAFT_OBJECTIVES, Objective
from app.segmentation.service import ClassificationService

AS_OF = date(2026, 11, 15)

#: customer -> (objective, allowed offer, billing stage)    — from §16
EXPECTED = {
    "C0001": (Objective.APPRECIATION, None, None),
    "C0002": (Objective.LOYALTY_REWARD, "OFF-LOY-200", None),
    "C0003": (Objective.REENGAGEMENT, "OFF-RE-5GB", None),
    "C0004": (Objective.WINBACK, "OFF-RE-5GB", None),
    "C0005": (Objective.BILLING_REMINDER_COURTEOUS, None, 1),
    "C0006": (Objective.BILLING_REMINDER_FIRM, None, 3),
    "C0007": (Objective.NO_CONTACT_BY_POLICY, None, None),
    "C0008": (Objective.REENGAGEMENT, "OFF-RE-5GB", None),  # the unsafe output is M3's demo
    "C0009": (Objective.BILLING_REMINDER_FOLLOWUP, None, 2),
    "C0010": (Objective.ESCALATE, None, None),
}


@pytest.fixture
def pipeline(demo_session):
    classify = ClassificationService.from_session(demo_session)
    policy = PolicyService.from_session(demo_session)

    def run(cid: str):
        out = classify.classify(cid, AS_OF, persist=False)
        return out, policy.analyze(out.profile, out.features, out.result), policy

    return run


@pytest.mark.parametrize("cid", sorted(EXPECTED))
def test_demo_customer_strategy(pipeline, cid):
    objective, offer_id, stage = EXPECTED[cid]
    _, analysis, _ = pipeline(cid)
    s = analysis.strategy
    assert s.objective is objective
    assert (s.allowed_offer.offer_id if s.allowed_offer else None) == offer_id
    assert s.reminder_stage == stage


@pytest.mark.parametrize("cid", sorted(EXPECTED))
def test_classification_flag_and_billing_engine_agree(pipeline, cid):
    """PAYMENT_REMINDER (M1) is set exactly when the billing engine (M2) sees an overdue bill."""
    out, analysis, _ = pipeline(cid)
    flagged = "PAYMENT_REMINDER" in {s.value for s in out.result.segments}
    overdue = analysis.billing.state.value in {"OVERDUE", "PARTIALLY_PAID_OVERDUE"}
    assert flagged == overdue
    assert out.features.current_bill_state is analysis.billing.state


@pytest.mark.parametrize("cid", sorted(EXPECTED))
def test_llm_input_is_built_only_for_draftable_customers(pipeline, cid):
    out, analysis, policy = pipeline(cid)
    if analysis.strategy.objective in NON_DRAFT_OBJECTIVES:
        with pytest.raises(NotDraftableError):
            policy.llm_input.build(out.profile, out.result, analysis.billing, analysis.strategy)
        return
    inp = policy.llm_input.build(out.profile, out.result, analysis.billing, analysis.strategy)
    dumped = inp.model_dump_json()
    assert out.profile.email not in dumped and out.profile.customer_id not in dumped
    assert inp.allowed_slots["first_name"] == out.profile.first_name
    assert inp.objective is analysis.strategy.objective


def test_c0009_reward_is_deferred_not_lost(pipeline):
    _, analysis, _ = pipeline("C0009")
    rejected = {e.offer_id: e.failed_checks for e in analysis.offers.rejected}
    assert rejected["OFF-LOY-200"] == ["OFFER_BLOCKED_BY_BILLING"]
    assert analysis.strategy.suppressed[0].objective is Objective.LOYALTY_REWARD


def test_c0007_refusal_reasons(pipeline):
    _, analysis, _ = pipeline("C0007")
    assert "CONTACT_EMAIL_OPT_OUT" in analysis.strategy.rationale_codes
    assert analysis.strategy.template_id is None


def test_c0006_reminder_facts(pipeline):
    out, analysis, policy = pipeline("C0006")
    inp = policy.llm_input.build(out.profile, out.result, analysis.billing, analysis.strategy)
    assert inp.allowed_slots["amount_due"] == "₹749.00"
    assert inp.allowed_slots["due_date"] == "20 Oct 2026"
    assert inp.allowed_slots["days_overdue"] == "26"
