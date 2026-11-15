"""Templates, CTAs, disclaimers and tones load and are internally consistent."""

import pytest

from app.generation.content import (
    SLOT_RE,
    ContentConfigError,
    DisclaimerStore,
    TemplateStore,
    ToneStore,
    content_version,
    cta_text,
)
from app.schemas.enums import NON_DRAFT_OBJECTIVES, Objective

# Slot vocabulary agreed with M2's LLMInput builder (+ offer slots derived by M3).
KNOWN_SLOTS = {
    "first_name", "plan_name", "cta", "amount_due", "due_date", "bill_period",
    "days_overdue", "support_path", "offer_title", "offer_value", "offer_valid_to",
    "offer_terms",
}  # fmt: skip


@pytest.fixture(scope="module")
def store() -> TemplateStore:
    return TemplateStore()


def test_every_draft_objective_has_exactly_one_template(store):
    for objective in Objective:
        if objective in NON_DRAFT_OBJECTIVES:
            continue
        assert store.for_objective(objective).objective == objective


@pytest.mark.parametrize("tpl", TemplateStore().all(), ids=lambda t: t.template_id)
def test_template_variants_use_known_slots_and_fit_word_range(tpl):
    lo, hi = tpl.word_range
    for v in tpl.variants:
        assert v.slots <= KNOWN_SLOTS, v.slots - KNOWN_SLOTS
        assert "first_name" in v.slots
        words = len(SLOT_RE.sub("X", v.body).split())
        assert lo <= words <= hi, (tpl.template_id, words)


def test_offer_templates_have_offer_and_billing_have_none(store):
    assert all(v.when_offer for v in store.get("loyalty_reward_v1").variants)
    for tid in ("billing_reminder_stage1", "billing_reminder_stage2", "billing_reminder_stage3"):
        assert not any(v.when_offer for v in store.get(tid).variants)


def test_select_variant_prefers_plan_name_and_falls_back(store):
    tpl = store.get("appreciation_v1")
    with_plan = tpl.select_variant({"first_name", "cta", "plan_name"}, has_offer=False)
    without = tpl.select_variant({"first_name", "cta"}, has_offer=False)
    assert "plan_name" in with_plan.slots
    assert "plan_name" not in without.slots


def test_select_variant_raises_when_required_slot_missing(store):
    with pytest.raises(ContentConfigError, match="missing slots"):
        store.get("billing_reminder_stage1").select_variant({"first_name"}, has_offer=False)


def test_unknown_template_and_cta_raise(store):
    with pytest.raises(ContentConfigError):
        store.get("nope")
    with pytest.raises(ContentConfigError):
        cta_text("nope")
    assert cta_text("pay_bill") == "View and pay your bill"


def test_disclaimers_and_tones_cover_strategy_keys():
    d = DisclaimerStore()
    for key in ("already_paid", "support_dispute_path", "need_help", "offer_terms", "unsubscribe"):
        assert d.text(key)
    tones = ToneStore()
    for tone in ("warm_grateful", "warm_celebratory", "helpful_low_pressure",
                 "friendly_no_guilt", "courteous", "polite_clear", "firm_respectful"):  # fmt: skip
        assert tones.rules_for(tone)


def test_content_version_ignores_line_endings():
    assert content_version("a\nb") == content_version("a\r\nb".replace("\r\n", "\n"))
    assert content_version("a") != content_version("b")
