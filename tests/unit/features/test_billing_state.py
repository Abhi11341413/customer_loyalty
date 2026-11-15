from datetime import date

import pytest

from app.features.billing_state import current_bill, derive_bill_state
from app.schemas.customer import BillingRecord, Payment
from app.schemas.enums import BillConflictType, BillState

AS_OF = date(2026, 11, 15)


def bill(period="2026-10", due=date(2026, 11, 10), amount=59900, status="UNPAID", dispute="NONE"):
    return BillingRecord(
        bill_id=f"B-{period}", billing_period=period, issue_date=date(2026, 10, 27),
        due_date=due, amount_due_minor=amount, status=status, dispute_status=dispute,
    )  # fmt: skip


def pay(amount, when=date(2026, 11, 1), bill_id="B-2026-10"):
    return Payment(payment_id=f"P{amount}{when}", bill_id=bill_id, paid_date=when,
                   amount_paid_minor=amount)  # fmt: skip


@pytest.mark.parametrize(
    "b, pays, state, conflict, days",
    [
        (bill(status="PAID"), [pay(59900)], BillState.PAID, None, None),
        (bill(status="WAIVED"), [], BillState.PAID, None, None),
        (bill(due=date(2026, 11, 20)), [], BillState.NOT_YET_DUE, None, None),
        (bill(due=date(2026, 11, 15)), [], BillState.NOT_YET_DUE, None, None),  # due today
        (bill(due=date(2026, 11, 14)), [], BillState.OVERDUE, None, 1),
        (bill(), [], BillState.OVERDUE, None, 5),
        (bill(status="PARTIALLY_PAID"), [pay(30000)], BillState.PARTIALLY_PAID_OVERDUE, None, 5),
        (bill(dispute="OPEN"), [], BillState.DISPUTED, None, None),
        (bill(due=None), [], BillState.DATA_CONFLICT, BillConflictType.MISSING_FIELD, None),
        (bill(status="PAID"), [pay(30000)], BillState.DATA_CONFLICT,
         BillConflictType.STATUS_PAYMENT_MISMATCH, None),
        (bill(status="PAID"), [pay(69900)], BillState.DATA_CONFLICT,
         BillConflictType.OVERPAYMENT, None),
        (bill(status="UNPAID"), [pay(59900)], BillState.DATA_CONFLICT,
         BillConflictType.STATUS_PAYMENT_MISMATCH, None),
    ],
)  # fmt: skip
def test_bill_state_table(b, pays, state, conflict, days):
    ev = derive_bill_state(b, pays, AS_OF)
    assert ev.state == state
    assert ev.conflict == conflict
    assert ev.days_overdue == days


def test_outstanding_is_amount_minus_payments():
    ev = derive_bill_state(bill(status="PARTIALLY_PAID"), [pay(30000)], AS_OF)
    assert ev.outstanding_minor == 29900


def test_payment_after_as_of_is_ignored():
    ev = derive_bill_state(bill(), [pay(59900, when=date(2026, 11, 20))], AS_OF)
    assert ev.state == BillState.OVERDUE


def test_grace_days_shift_overdue():
    assert derive_bill_state(bill(), [], AS_OF, grace_days=5).state == BillState.NOT_YET_DUE
    assert derive_bill_state(bill(), [], AS_OF, grace_days=4).days_overdue == 1


def test_current_bill_prefers_oldest_overdue_over_newer_not_yet_due():
    old = bill("2026-10", due=date(2026, 10, 20))
    new = BillingRecord(bill_id="B-2026-11", billing_period="2026-11",
                        issue_date=date(2026, 11, 5), due_date=date(2026, 11, 20),
                        amount_due_minor=59900, status="UNPAID")  # fmt: skip
    ev = current_bill([old, new], [], AS_OF)
    assert ev.bill.bill_id == "B-2026-10" and ev.days_overdue == 26


def test_current_bill_dispute_wins_and_no_bills_is_none():
    paid = bill("2026-09", status="PAID")
    disputed = bill("2026-10", dispute="OPEN")
    pays = [pay(59900, bill_id="B-2026-09")]
    assert current_bill([paid, disputed], pays, AS_OF).state == BillState.DISPUTED
    assert current_bill([], [], AS_OF) is None


def test_old_bills_outside_lookback_are_ignored():
    ancient = BillingRecord(bill_id="B-old", billing_period="2026-01",
                            issue_date=date(2026, 1, 27), due_date=None,
                            amount_due_minor=100, status="UNPAID")  # fmt: skip
    assert current_bill([ancient], [], AS_OF, lookback_months=3) is None
