from datetime import UTC, date, datetime

from app.features.builder import FeatureBuilder, tenure_months
from app.schemas.customer import (
    ActivityMonth,
    BillingRecord,
    CommunicationRecord,
    CustomerProfile,
    Payment,
    PlanSubscription,
)
from app.schemas.enums import BillState

AS_OF = date(2026, 11, 15)
MONTHS = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]


def profile(usage=(40, 40, 40, 14, 14, 14), bills=None, payments=None, **kw) -> CustomerProfile:
    activity = [
        ActivityMonth(month=m, active_days=min(28, max(u // 2, 0)), usage_events=u,
                      last_activity_date=date(int(m[:4]), int(m[5:]), 28) if u else None)
        for m, u in zip(MONTHS, usage, strict=True)
    ]  # fmt: skip
    base = dict(
        customer_id="C9999", as_of_date=AS_OF, first_name="Test", email="t.c9999@example.test",
        customer_since=date(2024, 4, 10), account_status="ACTIVE",
        plans=[PlanSubscription(customer_plan_id="CP1", plan_id="PL-POST-499",
                                plan_name="Postpaid 499", plan_category="POSTPAID",
                                start_date=date(2024, 4, 10), status="ACTIVE")],
        activity=activity, bills=bills or [], payments=payments or [],
    )  # fmt: skip
    base.update(kw)
    return CustomerProfile(**base)


def monthly_bills(n=12, unpaid=(), late=()):
    bills, pays = [], []
    for i in range(n):
        idx = 2026 * 12 + 9 - i  # Oct 2026 backwards
        y, m = idx // 12, idx % 12 + 1
        nxt = idx + 1
        due = date(nxt // 12, nxt % 12 + 1, 10)
        bid = f"B-{y}-{m:02d}"
        bills.append(BillingRecord(bill_id=bid, billing_period=f"{y}-{m:02d}",
                                   issue_date=date(y, m, 27), due_date=due,
                                   amount_due_minor=49900,
                                   status="UNPAID" if i in unpaid else "PAID"))  # fmt: skip
        if i not in unpaid:
            when = date.fromordinal(due.toordinal() + (5 if i in late else -3))
            pays.append(Payment(payment_id=f"P{i}", bill_id=bid, paid_date=when,
                                amount_paid_minor=49900))  # fmt: skip
    return bills, pays


def test_tenure_months():
    assert tenure_months(date(2024, 4, 10), AS_OF) == 31
    assert tenure_months(date(2026, 10, 16), AS_OF) == 0
    assert tenure_months(date(2025, 11, 15), AS_OF) == 12
    assert tenure_months(date(2025, 11, 16), AS_OF) == 11


def test_activity_features():
    f = FeatureBuilder().build(profile())
    assert f.recent_activity_avg == 14.0
    assert f.prior_activity_avg == 40.0
    assert f.activity_trend_ratio == 0.35
    assert f.months_observed == 6
    assert f.active_months_last_6 == 6
    assert f.days_since_last_activity == (AS_OF - date(2026, 10, 28)).days
    assert f.activity_cv_6m is not None and f.activity_cv_6m > 0.4


def test_trend_null_when_prior_zero_and_listed_missing():
    f = FeatureBuilder().build(profile(usage=(0, 0, 0, 10, 10, 10)))
    assert f.activity_trend_ratio is None
    assert "activity_trend_ratio" in f.missing_features


def test_payment_features():
    bills, pays = monthly_bills(12, unpaid={0}, late={2})
    f = FeatureBuilder().build(profile(bills=bills, payments=pays))
    assert f.bills_last_12m == 12
    assert f.on_time_bills_last_12m == 10
    assert f.on_time_payment_rate_12m == round(10 / 12, 4)
    assert f.late_payments_last_6m == 1
    assert f.current_bill_state == BillState.OVERDUE
    assert f.days_overdue == 5
    assert f.outstanding_minor == 49900


def test_no_activity_rows_lists_missing_features():
    f = FeatureBuilder().build(profile(activity=[]))
    assert f.months_observed == 0
    for name in ("recent_activity_avg", "prior_activity_avg", "days_since_last_activity"):
        assert name in f.missing_features


def test_leakage_future_data_is_ignored():
    """Payments, bills, activity and comms dated after as_of must not affect features."""
    bills, pays = monthly_bills(12, unpaid={0})
    future_pay = Payment(payment_id="PF", bill_id=bills[0].bill_id, paid_date=date(2026, 11, 20),
                         amount_paid_minor=49900)  # fmt: skip
    future_bill = BillingRecord(bill_id="B-future", billing_period="2026-11",
                                issue_date=date(2026, 11, 27), due_date=date(2026, 12, 10),
                                amount_due_minor=49900, status="UNPAID")  # fmt: skip
    p = profile(bills=bills + [future_bill], payments=pays + [future_pay])
    p = p.model_copy(update={
        "activity": p.activity + [ActivityMonth(month="2026-12", active_days=20,
                                                usage_events=99,
                                                last_activity_date=date(2026, 12, 2))],
        "communications": [CommunicationRecord(comm_id="X", sent_at=datetime(2026, 12, 1,
                                               tzinfo=UTC), channel="EMAIL", category="SERVICE",
                                               objective="BILLING_REMINDER",
                                               source="HISTORICAL_SEED")],
    })  # fmt: skip
    f = FeatureBuilder().build(p)
    assert f.current_bill_state == BillState.OVERDUE  # the future payment did not "pay" it
    assert f.current_bill_id == bills[0].bill_id
    assert f.days_since_last_activity > 0
    assert f.on_time_bills_last_12m == 11


def test_negative_counts_are_clipped_and_flagged():
    p = profile()
    bad = p.activity[:-1] + [ActivityMonth(month="2026-10", active_days=-1, usage_events=-5)]
    f = FeatureBuilder().build(p.model_copy(update={"activity": bad}))
    assert any(flag.startswith("NEGATIVE_ACTIVITY_CLIPPED") for flag in f.data_quality_flags)
    assert f.recent_activity_avg == round((14 + 14 + 0) / 3, 4)


def test_builder_is_deterministic():
    bills, pays = monthly_bills(12)
    p = profile(bills=bills, payments=pays)
    assert FeatureBuilder().build(p) == FeatureBuilder().build(p)
