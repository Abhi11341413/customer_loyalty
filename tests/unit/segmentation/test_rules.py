"""Segment rules incl. boundaries. Thresholds come from config/policies/segments.yaml."""

import pytest

from app.schemas.enums import BillConflictType, BillState, ConfidenceBand, Segment
from app.segmentation.engine import SegmentationEngine

S = Segment


@pytest.fixture(scope="module")
def engine():
    return SegmentationEngine()


def segs(engine, f):
    return engine.classify(f).segments


def codes(engine, f):
    return [r.code for r in engine.classify(f).reason_codes]


def test_consistent(engine, make_features):
    f = make_features(active_months_last_6=6, activity_cv_6m=0.2, on_time_payment_rate_12m=0.92,
                      activity_trend_ratio=1.0)  # fmt: skip
    assert segs(engine, f) == [S.CONSISTENT]
    assert {"ENG_ACTIVE_MONTHS", "PAY_ON_TIME_RATE"} <= set(codes(engine, f))


def test_loyalty(engine, make_features):
    f = make_features(tenure_months=31, late_payments_last_6m=0, on_time_payment_rate_12m=1.0)
    r = engine.classify(f)
    assert r.segments == [S.CONSISTENT, S.LOYALTY_CANDIDATE]
    assert r.primary_segment == S.LOYALTY_CANDIDATE
    assert {"LOY_TENURE_MONTHS", "LOY_PERFECT_RECENT_PAYMENTS"} <= {c.code for c in r.reason_codes}


def test_declining(engine, make_features):
    f = make_features(prior_activity_avg=40.0, recent_activity_avg=14.0, activity_trend_ratio=0.35)
    r = engine.classify(f)
    assert r.segments == [S.DECLINING_ACTIVITY]
    drop = next(c for c in r.reason_codes if c.code == "ENG_ACTIVITY_DROP_PCT")
    assert drop.params["drop_pct"] == 65
    assert "65%" in drop.text and "40.0 → 14.0" in drop.text


def test_dormant(engine, make_features):
    f = make_features(days_since_last_activity=92, recent_activity_avg=5.0)
    assert segs(engine, f) == [S.DORMANT]
    assert "ENG_INACTIVE_DAYS" in codes(engine, f)


def test_dormant_by_zero_recent_activity(engine, make_features):
    f = make_features(days_since_last_activity=40, recent_activity_avg=0.0,
                      activity_trend_ratio=0.0)  # fmt: skip
    assert segs(engine, f) == [S.DORMANT]
    assert "ENG_ZERO_RECENT_ACTIVITY" in codes(engine, f)


def test_overdue_sets_payment_reminder(engine, make_features):
    f = make_features(current_bill_state=BillState.OVERDUE, days_overdue=25)
    r = engine.classify(f)
    assert S.PAYMENT_REMINDER in r.segments
    assert r.primary_segment == S.PAYMENT_REMINDER


def test_partial_payment_reason(engine, make_features):
    f = make_features(current_bill_state=BillState.PARTIALLY_PAID_OVERDUE, days_overdue=8,
                      outstanding_minor=29900)  # fmt: skip
    r = engine.classify(f)
    partial = next(c for c in r.reason_codes if c.code == "BILL_PARTIAL_PAYMENT")
    assert "₹299.00" in partial.text


def test_conflicting_indicators_dormant_wins_and_no_loyalty(engine, make_features):
    f = make_features(days_since_last_activity=92, tenure_months=40, on_time_payment_rate_12m=1.0)
    assert segs(engine, f) == [S.DORMANT]  # loyalty requires CONSISTENT


def test_missing_activity_is_insufficient_data_low_confidence(engine, make_features):
    f = make_features(
        months_observed=0, active_months_last_6=0, recent_activity_avg=None,
        prior_activity_avg=None, activity_trend_ratio=None, activity_cv_6m=None,
        days_since_last_activity=None,
        missing_features=["recent_activity_avg", "prior_activity_avg", "activity_trend_ratio",
                          "activity_cv_6m", "days_since_last_activity"],
    )  # fmt: skip
    r = engine.classify(f)
    assert r.segments == [S.INSUFFICIENT_DATA]
    assert r.confidence_band == ConfidenceBand.LOW
    assert "recent_activity_avg" in r.missing_features


def test_new_customer_is_insufficient_not_dormant(engine, make_features):
    f = make_features(tenure_months=1, months_observed=1, days_since_last_activity=90)
    assert segs(engine, f) == [S.INSUFFICIENT_DATA]


def test_standard_when_irregular(engine, make_features):
    f = make_features(activity_cv_6m=0.9, on_time_payment_rate_12m=0.7)
    r = engine.classify(f)
    assert r.segments == [S.STANDARD]
    assert [c.code for c in r.reason_codes] == ["ENG_NO_TARGET_PATTERN"]


@pytest.mark.parametrize("state, code", [
    (BillState.DISPUTED, "BILL_DISPUTED"),
    (BillState.DATA_CONFLICT, "BILL_DATA_CONFLICT"),
])  # fmt: skip
def test_disputed_or_conflict_never_sets_reminder(engine, make_features, state, code):
    f = make_features(current_bill_state=state,
                      bill_conflict_type=BillConflictType.OVERPAYMENT
                      if state == BillState.DATA_CONFLICT else None)  # fmt: skip
    r = engine.classify(f)
    assert S.PAYMENT_REMINDER not in r.segments
    assert code in [c.code for c in r.reason_codes]


# ------------------------------------------------------------------ boundaries (exact YAML side)
@pytest.mark.parametrize("days, expected", [(59, S.CONSISTENT), (60, S.DORMANT), (61, S.DORMANT)])
def test_dormant_boundary(engine, make_features, days, expected):
    assert segs(engine, make_features(days_since_last_activity=days))[0] == expected


@pytest.mark.parametrize("ratio, expected", [
    (0.69, S.DECLINING_ACTIVITY), (0.70, S.DECLINING_ACTIVITY), (0.71, S.CONSISTENT),
])  # fmt: skip
def test_decline_ratio_boundary(engine, make_features, ratio, expected):
    f = make_features(activity_trend_ratio=ratio, prior_activity_avg=40.0,
                      recent_activity_avg=40.0 * ratio)  # fmt: skip
    assert segs(engine, f)[0] == expected


@pytest.mark.parametrize("prior, expected", [(4.9, S.CONSISTENT), (5.0, S.DECLINING_ACTIVITY)])
def test_decline_needs_prior_baseline(engine, make_features, prior, expected):
    f = make_features(activity_trend_ratio=0.5, prior_activity_avg=prior,
                      recent_activity_avg=prior / 2)  # fmt: skip
    # with prior < 5 and trend 0.5, the CONSISTENT trend condition fails too -> STANDARD
    got = segs(engine, f)[0]
    assert got == (S.STANDARD if expected == S.CONSISTENT else expected)


@pytest.mark.parametrize("rate, expected", [(0.79, S.STANDARD), (0.80, S.CONSISTENT)])
def test_on_time_rate_boundary(engine, make_features, rate, expected):
    assert segs(engine, make_features(on_time_payment_rate_12m=rate))[0] == expected


@pytest.mark.parametrize("months, expected", [(4, S.STANDARD), (5, S.CONSISTENT)])
def test_active_months_boundary(engine, make_features, months, expected):
    assert segs(engine, make_features(active_months_last_6=months))[0] == expected


@pytest.mark.parametrize("tenure, loyal", [(11, False), (12, True)])
def test_loyalty_tenure_boundary(engine, make_features, tenure, loyal):
    assert (S.LOYALTY_CANDIDATE in segs(engine, make_features(tenure_months=tenure))) == loyal


@pytest.mark.parametrize("rate, loyal", [(0.89, False), (0.90, True)])
def test_loyalty_rate_boundary(engine, make_features, rate, loyal):
    f = make_features(tenure_months=20, on_time_payment_rate_12m=rate)
    assert (S.LOYALTY_CANDIDATE in segs(engine, f)) == loyal


def test_one_late_payment_blocks_loyalty(engine, make_features):
    f = make_features(tenure_months=20, late_payments_last_6m=1)
    assert segs(engine, f) == [S.CONSISTENT]


def test_missing_on_time_rate_cannot_be_consistent(engine, make_features):
    f = make_features(on_time_payment_rate_12m=None, missing_features=["on_time_payment_rate_12m"])
    assert segs(engine, f) == [S.STANDARD]


def test_engagement_is_exactly_one(engine, make_features):
    engagement = {S.INSUFFICIENT_DATA, S.DORMANT, S.DECLINING_ACTIVITY, S.CONSISTENT, S.STANDARD}
    for f in (make_features(), make_features(days_since_last_activity=90),
              make_features(tenure_months=1)):  # fmt: skip
        assert len(set(engine.classify(f).segments) & engagement) == 1
