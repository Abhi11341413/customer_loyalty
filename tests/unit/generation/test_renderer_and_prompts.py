"""SlotRenderer, apply_edit, content hash, PromptRegistry."""

import pytest

from app.generation.content import ContentConfigError
from app.generation.prompts.registry import PromptRegistry
from app.generation.renderer import (
    DISCLAIMER_SEPARATOR,
    apply_edit,
    compute_content_hash,
    split_disclaimers,
)
from app.schemas.enums import Objective
from tests.support import m3

BILL = Objective.BILLING_REMINDER_COURTEOUS


def test_slots_filled_with_verified_values_and_recorded():
    d = m3.rendered(BILL)
    assert "₹599.00" in d.body and "10 Nov 2026" in d.body and "October 2026" in d.subject
    assert "{{" not in d.subject + d.body
    assert d.facts_used["amount_due"] == "₹599.00"
    assert d.unknown_slots == []


def test_disclaimers_appended_verbatim_after_separator():
    d = m3.rendered(BILL)
    main, block = split_disclaimers(d.body)
    assert "If you have already paid this bill, please ignore this email." in block
    assert m3.SUPPORT_PATH in block
    assert d.disclaimer_keys_appended == ["already_paid", "support_dispute_path"]
    assert "please ignore" not in main


def test_offer_slots_derived_from_verified_offer():
    d = m3.rendered(Objective.LOYALTY_REWARD)
    assert "Loyalty credit" in d.body and "₹200.00" in d.body and "31 Dec 2026" in d.body
    assert "One-time ₹200 bill credit" in d.body  # offer_terms disclaimer
    assert d.facts_used["offer_value"] == "₹200.00"


def test_unknown_slot_is_kept_and_listed_not_silently_dropped():
    raw = m3.template_raw(BILL).model_copy(update={"body": "Hi {{first_name}}, pay {{late_fee}}."})
    d = m3.renderer().render(raw, m3.llm_input(BILL))
    assert "{{late_fee}}" in d.body
    assert d.unknown_slots == ["late_fee"]


def test_no_disclaimer_block_when_none_required():
    li = m3.llm_input(Objective.APPRECIATION, required_disclaimers=[])
    d = m3.renderer().render(m3.template_raw(Objective.APPRECIATION, li), li)
    assert DISCLAIMER_SEPARATOR not in d.body


def test_content_hash_binds_subject_and_body():
    d = m3.rendered(BILL)
    assert d.content_hash == compute_content_hash(d.subject, d.body)
    assert d.content_hash.startswith("sha256:")
    assert compute_content_hash("a", "b") != compute_content_hash("a", "b ")


def test_apply_edit_rehashes_and_flags_typed_slots():
    d = m3.rendered(BILL)
    e = apply_edit(d, "  New   subject ", d.body + "\nSee {{pay_link}}")
    assert e.subject == "New subject" and e.edited
    assert e.content_hash != d.content_hash
    assert e.unknown_slots == ["pay_link"]
    assert e.raw == d.raw


# --------------------------------------------------------------------------- prompts


def test_prompt_version_is_stable_and_content_addressed():
    a, b = PromptRegistry(), PromptRegistry()
    assert a.version == b.version and a.version.startswith("v1+")


def test_prompt_with_offer_names_offer_and_offer_slots():
    p = PromptRegistry().render(m3.llm_input(Objective.LOYALTY_REWARD))
    assert 'offer_id "OFF-LOY-200"' in p.user
    assert "{{offer_value}}" in p.user and "{{offer_terms}}" in p.user
    assert "Do not write disclaimers yourself" in p.system


def test_prompt_without_offer_forbids_offer_talk():
    p = PromptRegistry().render(m3.llm_input(BILL))
    assert "There is NO offer" in p.user
    assert '"offer_id": null' in p.user


def test_missing_guidance_raises():
    with pytest.raises(ContentConfigError):
        PromptRegistry().guidance_for("NO_CONTACT")
