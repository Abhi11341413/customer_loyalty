"""Every guardrail check: clean drafts pass, each injected defect is caught (§15.2)."""

import pytest

from app.generation.renderer import DISCLAIMER_SEPARATOR, apply_edit, split_disclaimers
from app.schemas.enums import ConfidenceBand, Objective, Severity
from tests.support import m3

BILL1 = Objective.BILLING_REMINDER_COURTEOUS
BILL3 = Objective.BILLING_REMINDER_FIRM
LOY = Objective.LOYALTY_REWARD
APP = Objective.APPRECIATION
RE = Objective.REENGAGEMENT


def validate(draft, objective, **ctx_kw):
    return m3.runner().validate(draft, m3.ctx(objective, **ctx_kw))


def failed_ids(report):
    return {f.check_id for f in report.failures}


def inject(objective, sentence, subject=None):
    """Add a sentence to the main body (before disclaimers), like an LLM would."""
    d = m3.rendered(objective)
    main, block = split_disclaimers(d.body)
    lines = main.split("\n\n")
    lines.insert(2, sentence)
    body = "\n\n".join(lines) + (DISCLAIMER_SEPARATOR + block if block else "")
    return apply_edit(d, subject or d.subject, body)


# --------------------------------------------------------------------------- false-positive guard


@pytest.mark.parametrize("objective", m3.DRAFT_OBJECTIVES)
def test_clean_template_draft_passes_every_check(objective):
    report = validate(
        m3.rendered(objective),
        objective,
        contact_allowed=True,
        duplicate_outreach=False,
        confidence_band=ConfidenceBand.HIGH,
        shadow_agrees=True,
    )
    assert report.overall is Severity.PASS, [f.message for f in report.failures]
    assert report.checks_skipped == []
    assert set(report.checks_run) == set(m3.runner().check_ids)


@pytest.mark.parametrize(
    "objective,sentence",
    [
        (BILL1, "We understand that things can slip through the cracks, and we are here to help."),
        (APP, "Feel free to reply with any questions about your account."),
        (RE, "Many customers enjoy streaming and browsing more with the extra data."),
        (LOY, "We hope you enjoy your reward."),
    ],
)
def test_natural_extra_prose_does_not_block(objective, sentence):
    assert validate(inject(objective, sentence), objective).overall is not Severity.BLOCK


# ---------------------------------------------------------------- injected defects (§14.4)


@pytest.mark.parametrize(
    "objective,sentence,check_id",
    [
        (BILL1, "The amount due is ₹699.00.", "AMOUNT_GROUNDED"),  # wrong amount
        (BILL1, "A late charge of Rs 50 may apply.", "AMOUNT_GROUNDED"),  # extra amount
        (BILL1, "It was due on 12 Nov 2026.", "DATE_GROUNDED"),  # wrong date
        (BILL1, "Please pay within 24 hours.", "DATE_GROUNDED"),  # relative deadline
        (BILL1, "Please settle it by tomorrow.", "DATE_GROUNDED"),
        (APP, "Enjoy 20% off your next bill.", "NUMBER_GROUNDED"),  # invented discount
        (APP, "Enjoy 20% off your next bill.", "OFFER_ID_VALID"),  # offer when none allowed
        (APP, "Thank you for your 10 years with us.", "NUMBER_GROUNDED"),  # unsupported claim
        (LOY, "Use code OFF-LOY-999 to redeem.", "OFFER_ID_VALID"),  # wrong offer id
        (BILL1, "As a thank-you, enjoy a bonus data pack.", "OFFER_ID_VALID"),  # offer in reminder
        (BILL3, "Failure to pay will lead to legal action.", "BLOCKED_LANGUAGE"),  # threat
        (BILL3, "This may affect your credit score.", "BLOCKED_LANGUAGE"),
        (BILL3, "A late fee will be added.", "BLOCKED_LANGUAGE"),
        (RE, "We noticed you have not been using your plan.", "BLOCKED_LANGUAGE"),
        (BILL1, "Call us on +91 98765 43210.", "PII_LEAKAGE"),  # phone number
        (BILL1, "We also emailed priya.c0003@example.test.", "PII_LEAKAGE"),  # other customer
        (APP, "You are in our LOYALTY_CANDIDATE group.", "PII_LEAKAGE"),  # internal segment
        (APP, "Reason: ENG_ACTIVE_MONTHS.", "PII_LEAKAGE"),  # internal code
        (BILL1, "Thank you for your payment.", "FACT_CONTRADICTION"),  # paid in overdue
        (APP, "Your bill is overdue.", "FACT_CONTRADICTION"),  # billing talk in marketing
        (BILL1, "Please pay {{late_fee}} as well.", "UNKNOWN_SLOT"),
    ],
)
def test_injected_defect_is_blocked(objective, sentence, check_id):
    report = validate(inject(objective, sentence), objective)
    assert check_id in failed_ids(report)
    assert report.overall is Severity.BLOCK
    hit = next(f for f in report.failures if f.check_id == check_id)
    assert hit.severity is Severity.BLOCK and hit.mandatory
    if hit.span is not None:
        text = getattr(inject(objective, sentence), hit.field)
        assert text[hit.start : hit.end] == hit.span


def test_verified_facts_are_not_flagged():
    """The real amount/date/offer values and the support path are grounded."""
    report = validate(inject(BILL1, "Again, ₹599.00 was due on 10 Nov 2026."), BILL1)
    assert report.overall is Severity.PASS
    report = validate(inject(LOY, "Your Loyalty credit of ₹200.00 lasts until 31 Dec 2026."), LOY)
    assert report.overall is Severity.PASS


def test_days_overdue_bare_number_is_grounded_but_other_days_are_not():
    assert validate(inject(BILL3, "That is 26 days past the due date."), BILL3).overall is not (
        Severity.BLOCK
    )
    assert "NUMBER_GROUNDED" in failed_ids(validate(inject(BILL3, "You have 7 days left."), BILL3))


def test_helpline_inside_verified_support_path_is_allowed():
    li = m3.llm_input(
        BILL1,
        allowed_slots={
            **m3.llm_input(BILL1).allowed_slots,
            "support_path": "call our helpline on 1800 123 4567 or reply to this email.",
        },
    )
    d = m3.rendered(BILL1, li)
    assert m3.runner().validate(d, m3.ctx(BILL1, li)).overall is Severity.PASS


def test_greeting_to_another_name_is_pii():
    d = m3.rendered(BILL1)
    e = apply_edit(d, d.subject, d.body.replace("Hi Ravi", "Hi Priya"))
    assert "PII_LEAKAGE" in failed_ids(validate(e, BILL1))


def test_removed_disclaimer_and_support_path_block():
    d = m3.rendered(BILL1)
    main, _ = split_disclaimers(d.body)
    report = validate(apply_edit(d, d.subject, main), BILL1)
    assert {"DISCLAIMER_PRESENT", "SUPPORT_PATH_PRESENT"} <= failed_ids(report)


def test_altered_disclaimer_text_blocks():
    d = m3.rendered(LOY)
    e = apply_edit(d, d.subject, d.body.replace("applied on next bill", "applied soon"))
    assert "DISCLAIMER_PRESENT" in failed_ids(validate(e, LOY))


def test_billing_reminder_without_support_slot_blocks():
    slots = {k: v for k, v in m3.llm_input(BILL1).allowed_slots.items() if k != "support_path"}
    li = m3.llm_input(BILL1, allowed_slots=slots, required_disclaimers=["already_paid"])
    d = m3.rendered(BILL1, li)
    report = m3.runner().validate(d, m3.ctx(BILL1, li))
    assert "SUPPORT_PATH_PRESENT" in failed_ids(report)


def test_unknown_required_disclaimer_key_blocks():
    li = m3.llm_input(APP, required_disclaimers=["unsubscribe"])
    d = m3.rendered(APP, li)
    li2 = li.model_copy(update={"required_disclaimers": ["unsubscribe", "made_up"]})
    assert "DISCLAIMER_PRESENT" in failed_ids(m3.runner().validate(d, m3.ctx(APP, li2)))


def test_raw_offer_id_mismatch_and_objective_echo_block():
    d = m3.rendered(BILL1)
    bad = d.model_copy(
        update={"raw": d.raw.model_copy(update={"offer_id": "OFF-LOY-200",
                                                "communication_objective": "APPRECIATION"})}
    )  # fmt: skip
    assert {"OFFER_ID_VALID", "SCHEMA_VALID"} <= failed_ids(validate(bad, BILL1))


def test_empty_subject_blocks():
    d = m3.rendered(BILL1)
    assert "SCHEMA_VALID" in failed_ids(validate(apply_edit(d, "", d.body), BILL1))


def test_feel_free_is_not_an_offer():
    report = validate(inject(APP, "Feel free to get in touch, worry-free."), APP)
    assert "OFFER_ID_VALID" not in failed_ids(report)


# --------------------------------------------------------------------------- context checks


def test_consent_withdrawn_blocks_and_none_is_skipped():
    d = m3.rendered(APP)
    r = validate(d, APP, contact_allowed=False, contact_reasons=["CONTACT_EMAIL_OPT_OUT"])
    assert "CONSENT_STILL_VALID" in failed_ids(r) and r.overall is Severity.BLOCK
    assert "CONTACT_EMAIL_OPT_OUT" in next(
        f.message for f in r.failures if f.check_id == "CONSENT_STILL_VALID"
    )
    assert "CONSENT_STILL_VALID" in validate(d, APP).checks_skipped


def test_duplicate_outreach_blocks():
    assert "DUPLICATE_OUTREACH" in failed_ids(
        validate(m3.rendered(APP), APP, duplicate_outreach=True)
    )


def test_low_confidence_and_shadow_disagreement_warn_only():
    r = validate(m3.rendered(APP), APP, confidence_band=ConfidenceBand.LOW, shadow_agrees=False)
    assert r.overall is Severity.WARN
    assert [f.check_id for f in r.failures] == ["LOW_CONFIDENCE_SEGMENT"] * 2


# --------------------------------------------------------------------------- advisory checks


def test_urgency_in_courteous_reminder_warns_not_blocks():
    r = validate(inject(BILL1, "Please treat this as urgent."), BILL1)
    assert r.overall is Severity.WARN and failed_ids(r) == {"TONE_KEYWORDS"}
    assert r.approvable


def test_urgency_allowed_in_firm_reminder_but_casual_warns():
    assert validate(inject(BILL3, "Please treat this as urgent."), BILL3).overall is Severity.PASS
    r = validate(inject(BILL3, "No worries if you are busy."), BILL3)
    assert failed_ids(r) == {"TONE_KEYWORDS"}


def test_length_limits_warn():
    d = m3.rendered(BILL1)
    main, block = split_disclaimers(d.body)
    long_main = main + "\n\n" + "We value you. " * 60
    r = validate(apply_edit(d, d.subject, long_main + DISCLAIMER_SEPARATOR + block), BILL1)
    assert failed_ids(r) == {"LENGTH_LIMITS"} and r.overall is Severity.WARN
    short = apply_edit(d, d.subject, "Hi Ravi, pay." + DISCLAIMER_SEPARATOR + block)
    assert "LENGTH_LIMITS" in failed_ids(validate(short, BILL1))
