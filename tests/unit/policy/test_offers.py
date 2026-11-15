"""OfferEligibilityEngine: all 13 checks, each with a positive and negative case (§6.4, §15.2)."""

from datetime import date

import pytest

from app.policy import offers as o
from app.policy.offers import decide_offers, format_offer_value
from app.schemas.enums import AccountStatus, BillState, Segment
from tests.unit.policy.policy_factories import (
    AS_OF,
    campaign,
    loyal_customer,
    marketing,
    offer,
    redemption,
)


def run(customer=None, offers=None, campaigns=None, **kw):
    return decide_offers(
        customer or loyal_customer(),
        offers if offers is not None else [offer()],
        campaigns if campaigns is not None else [campaign()],
        as_of=AS_OF,
        **kw,
    )


def only_failures(decision):
    assert len(decision.rejected) == 1 and not decision.eligible
    return decision.rejected[0].failed_checks


def test_demo_c0002_offer_eligible_with_verified_display_values():
    d = run()
    assert [e.offer_id for e in d.eligible] == ["OFF-LOY-200"] and not d.rejected
    v = d.eligible[0].offer
    assert v.value_display == "₹200 bill credit"
    assert v.valid_to_display == "31 Dec 2026"
    assert v.terms_summary.startswith("One-time")
    assert d.selected_offer_id is None  # selection is the StrategySelector's job


def test_demo_c0002_expired_offer_rejected_alongside_valid_one():
    old = offer(offer_id="OFF-LOY-OLD", valid_from=date(2026, 1, 1), valid_to=date(2026, 6, 30))
    d = run(offers=[offer(), old])
    assert [e.offer_id for e in d.eligible] == ["OFF-LOY-200"]
    assert d.rejected[0].offer_id == "OFF-LOY-OLD"
    assert d.rejected[0].failed_checks == [o.OFFER_EXPIRED]
    assert d.rejected[0].offer is None


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"offers": [offer(valid_from=date(2026, 12, 1))]}, o.OFFER_NOT_STARTED),
        ({"offers": [offer(value=0)]}, o.OFFER_TERMS_INCOMPLETE),
        ({"offers": [offer(terms_summary="  ")]}, o.OFFER_TERMS_INCOMPLETE),
        ({"offers": [offer(channel="SMS")]}, o.OFFER_CHANNEL_MISMATCH),
        ({"offers": [offer(min_tenure_months=40)]}, o.OFFER_TENURE_SHORT),
        ({"offers": [offer(total_cap=37)]}, o.OFFER_CAP_REACHED),
        ({"campaigns": [campaign(status="PAUSED")]}, o.CAMPAIGN_NOT_ACTIVE),
        ({"campaigns": [campaign(end_date=date(2026, 11, 10))]}, o.CAMPAIGN_NOT_ACTIVE),
        ({"campaigns": []}, o.CAMPAIGN_DATA_MISSING),
        (
            {"customer": loyal_customer(segments=frozenset({Segment.CONSISTENT}))},
            o.OFFER_SEGMENT_INELIGIBLE,
        ),
        (
            {"customer": loyal_customer(account_status=AccountStatus.SUSPENDED)},
            o.ACCOUNT_NOT_ACTIVE,
        ),
        ({"offers": [offer(eligible_plan_ids=["PL-PRE-199"])]}, o.OFFER_PLAN_MISMATCH),
        ({"offers": [offer(offer_type="MYSTERY")]}, o.OFFER_TERMS_INCOMPLETE),
        ({"offers": [offer(value_type="CASHBACK")]}, o.OFFER_TERMS_INCOMPLETE),
        ({"redemptions": [redemption()]}, o.OFFER_REDEMPTION_LIMIT),
        ({"history": [marketing(10, offer_id="OFF-LOY-200")]}, o.OFFER_DUPLICATE_RECENT),
    ],
)
def test_each_failed_check(kwargs, code):
    assert only_failures(run(**kwargs)) == [code]


@pytest.mark.parametrize(
    "state",
    [
        BillState.OVERDUE,
        BillState.PARTIALLY_PAID_OVERDUE,
        BillState.DISPUTED,
        BillState.DATA_CONFLICT,
    ],
)
def test_blocked_by_billing(state):
    """Demo C0009: loyal customer with an overdue bill -> reward deferred."""
    assert only_failures(run(customer=loyal_customer(bill_state=state))) == [
        o.OFFER_BLOCKED_BY_BILLING
    ]


@pytest.mark.parametrize("state", [BillState.PAID, BillState.NOT_YET_DUE, BillState.NO_BILL])
def test_not_blocked_by_settled_billing(state):
    assert run(customer=loyal_customer(bill_state=state)).eligible


def test_overdue_allowed_when_offer_does_not_require_it():
    d = run(
        customer=loyal_customer(bill_state=BillState.OVERDUE),
        offers=[offer(requires_no_overdue=False)],
    )
    assert d.eligible


def test_channel_any_is_accepted():
    assert run(offers=[offer(channel="ANY")]).eligible


def test_matching_plan_passes_plan_check():
    assert run(offers=[offer(eligible_plan_ids=["PL-POST-499", "PL-X"])]).eligible


def test_redemption_by_other_customer_does_not_count():
    assert run(redemptions=[redemption(customer_id="C9999")]).eligible


def test_old_send_of_same_offer_is_not_a_duplicate():
    assert run(history=[marketing(30, offer_id="OFF-LOY-200")]).eligible


def test_tenure_exactly_minimum_passes():
    assert run(customer=loyal_customer(tenure_months=12)).eligible


def test_all_failures_are_collected():
    bad = offer(channel="SMS", valid_to=date(2026, 11, 1), min_tenure_months=99)
    fails = only_failures(run(offers=[bad], campaigns=[campaign(status="ENDED")]))
    assert set(fails) == {
        o.CAMPAIGN_NOT_ACTIVE,
        o.OFFER_EXPIRED,
        o.OFFER_CHANNEL_MISMATCH,
        o.OFFER_TENURE_SHORT,
    }


def test_unknown_candidate_ids():
    d = run(candidate_offer_ids=["OFF-NOPE", "bad id", "OFF-LOY-200"])
    assert [e.offer_id for e in d.eligible] == ["OFF-LOY-200"]
    assert {e.offer_id: e.failed_checks for e in d.rejected} == {
        "OFF-NOPE": [o.OFFER_NOT_FOUND],
        "bad id": [o.OFFER_ID_INVALID],
    }


def test_malformed_offer_id_in_catalogue_rejected():
    assert o.OFFER_ID_INVALID in only_failures(run(offers=[offer(offer_id="off_lower")]))


def test_results_are_sorted_by_offer_id():
    d = run(offers=[offer(offer_id="OFF-B"), offer(offer_id="OFF-A")])
    assert [e.offer_id for e in d.eligible] == ["OFF-A", "OFF-B"]


@pytest.mark.parametrize(
    ("value_type", "value", "text"),
    [
        ("PERCENT_DISCOUNT", 20, "20% off"),
        ("FLAT_CREDIT_MINOR", 20000, "₹200 bill credit"),
        ("FLAT_CREDIT_MINOR", 20050, "₹200.50 bill credit"),
        ("BONUS_DATA_GB", 5, "5 GB bonus data"),
        ("POINTS", 500, "500 bonus points"),
    ],
)
def test_value_display(value_type, value, text):
    assert format_offer_value(offer(value_type=value_type, value=value)) == text


def test_value_display_unknown_type_raises():
    with pytest.raises(ValueError):
        format_offer_value(offer(value_type="CASHBACK"))
