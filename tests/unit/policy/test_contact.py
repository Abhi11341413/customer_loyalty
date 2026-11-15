"""ContactPolicyGate: consent, blockers, frequency caps, duplicates (§6.5, §15.2)."""

import pytest

from app.policy import contact as c
from app.policy.config import load_contact_config
from app.policy.contact import check_contact
from app.schemas.enums import AccountStatus, MessageCategory
from tests.unit.policy.policy_factories import AS_OF, comm, days_ago, marketing, prefs

CFG = load_contact_config()
MKT, SVC = MessageCategory.MARKETING, MessageCategory.SERVICE


def check(
    p=None, category=MKT, objective="APPRECIATION", history=(), status=AccountStatus.ACTIVE, cfg=CFG
):
    return check_contact(
        p if p is not None else prefs(), status, history, category, objective, cfg, AS_OF
    )


def test_allowed_when_consented_and_quiet():
    d = check()
    assert d.allowed and d.reasons == [] and d.category is MKT


def test_demo_c0007_opted_out_lists_every_reason():
    d = check(
        prefs(
            email_opt_out=True,
            email_marketing_consent=False,
            email_service_consent=False,
            preferred_channel="NONE",
        )
    )
    assert not d.allowed
    assert d.reasons == [
        c.CONTACT_EMAIL_OPT_OUT,
        c.CONTACT_CHANNEL_NONE,
        c.CONTACT_NO_MARKETING_CONSENT,
    ]


def test_missing_preferences_never_guessed():
    d = check_contact(None, AccountStatus.ACTIVE, [], SVC, None, CFG, AS_OF)
    assert not d.allowed and d.reasons == [c.CONTACT_PREFERENCES_MISSING]


def test_closed_account_blocked():
    assert check(status=AccountStatus.CLOSED).reasons == [c.CONTACT_ACCOUNT_CLOSED]


def test_suspended_account_not_blocked_by_contact_gate():
    assert check(category=SVC, objective="BILLING_REMINDER", status=AccountStatus.SUSPENDED).allowed


def test_do_not_contact_until_future_date_blocks():
    assert check(prefs(do_not_contact_until=days_ago(-1))).reasons == [c.CONTACT_SUPPRESSED_UNTIL]


def test_do_not_contact_until_reached_allows():
    assert check(prefs(do_not_contact_until=AS_OF)).allowed


def test_marketing_needs_marketing_consent_even_with_service_consent():
    d = check(prefs(email_marketing_consent=False))
    assert d.reasons == [c.CONTACT_NO_MARKETING_CONSENT]


def test_service_reminder_allowed_without_marketing_consent():
    assert check(
        prefs(email_marketing_consent=False), category=SVC, objective="BILLING_REMINDER"
    ).allowed


def test_service_needs_service_consent():
    d = check(prefs(email_service_consent=False), category=SVC, objective="BILLING_REMINDER")
    assert d.reasons == [c.CONTACT_NO_SERVICE_CONSENT]


def test_sms_preference_does_not_block_email():
    assert check(prefs(preferred_channel="SMS")).allowed


def test_disabled_blocker_is_not_applied():
    cfg = CFG.model_copy(update={"global_blockers": []})
    assert check(prefs(email_opt_out=True), cfg=cfg).allowed


# --------------------------------------------------------------------------- frequency


def test_total_cap_per_30_days():
    history = [comm(d, objective=f"OBJ{d}", bill_id=None) for d in (1, 8, 15, 22)]
    d = check(category=SVC, objective="BILLING_REMINDER", history=history)
    assert d.reasons == [c.CONTACT_FREQUENCY_CAP]


def test_messages_older_than_30_days_do_not_count():
    history = [comm(d, objective=f"OBJ{d}", bill_id=None) for d in (30, 31, 40, 50)]
    assert check(category=SVC, objective="BILLING_REMINDER", history=history).allowed


@pytest.mark.parametrize(("ago", "allowed"), [(13, False), (14, True)])
def test_marketing_min_gap(ago, allowed):
    d = check(objective="WINBACK", history=[marketing(ago)])
    assert d.allowed is allowed
    if not allowed:
        assert d.reasons == [c.CONTACT_MARKETING_TOO_RECENT]


def test_marketing_gap_does_not_apply_to_service():
    assert check(category=SVC, objective="BILLING_REMINDER", history=[marketing(2)]).allowed


def test_service_email_does_not_trigger_marketing_gap():
    assert check(history=[comm(2, objective="BILLING_REMINDER")]).allowed


@pytest.mark.parametrize(("ago", "allowed"), [(6, False), (7, True)])
def test_duplicate_same_objective(ago, allowed):
    history = [comm(ago, objective="BILLING_REMINDER")]
    d = check(category=SVC, objective="BILLING_REMINDER_FOLLOWUP", history=history)
    assert d.allowed is allowed
    if not allowed:
        assert d.reasons == [c.CONTACT_DUPLICATE_OBJECTIVE]


def test_no_objective_skips_duplicate_check():
    assert check(category=SVC, objective=None, history=[comm(1)]).allowed


def test_future_history_ignored():
    assert check(history=[marketing(-3)]).allowed
