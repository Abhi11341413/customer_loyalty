"""Deterministic bill-state derivation (pure functions, no I/O).

Owner: M1, implementing the bill-state table agreed with M2. M2's BillingPolicyEngine should
import `derive_bill_state` / `current_bill` from here rather than re-implementing them, so the
classification flag and the reminder decision can never disagree.

Golden rule: never guess. Missing or contradictory data -> DATA_CONFLICT (escalate).
"""

from dataclasses import dataclass
from datetime import date

from app.schemas.customer import BillingRecord, Payment
from app.schemas.enums import BillConflictType, BillState

# Higher number = more urgent; used to pick the "current" bill among recent ones.
_SEVERITY = {
    BillState.DATA_CONFLICT: 6,
    BillState.DISPUTED: 5,
    BillState.PARTIALLY_PAID_OVERDUE: 4,
    BillState.OVERDUE: 4,
    BillState.NOT_YET_DUE: 2,
    BillState.PAID: 1,
}


@dataclass(frozen=True)
class BillEvaluation:
    bill: BillingRecord
    state: BillState
    paid_minor: int
    outstanding_minor: int
    days_overdue: int | None = None
    conflict: BillConflictType | None = None


def derive_bill_state(
    bill: BillingRecord, payments: list[Payment], as_of: date, grace_days: int = 0
) -> BillEvaluation:
    """Apply the bill-state rules in order to one bill. Payments after as_of are ignored."""
    paid = sum(p.amount_paid_minor for p in payments if p.bill_id == bill.bill_id
               and p.paid_date <= as_of)  # fmt: skip
    amount = bill.amount_due_minor
    outstanding = max(amount - paid, 0)

    def ev(state: BillState, conflict: BillConflictType | None = None, days: int | None = None):
        return BillEvaluation(bill, state, paid, outstanding, days, conflict)

    if bill.due_date is None or amount is None:
        return ev(BillState.DATA_CONFLICT, BillConflictType.MISSING_FIELD)
    if bill.dispute_status == "OPEN":
        return ev(BillState.DISPUTED)
    if bill.status == "PAID" and paid < amount:
        return ev(BillState.DATA_CONFLICT, BillConflictType.STATUS_PAYMENT_MISMATCH)
    if paid > amount:
        return ev(BillState.DATA_CONFLICT, BillConflictType.OVERPAYMENT)
    if bill.status == "UNPAID" and paid >= amount:
        return ev(BillState.DATA_CONFLICT, BillConflictType.STATUS_PAYMENT_MISMATCH)
    if bill.status == "WAIVED" or paid == amount:
        return ev(BillState.PAID)
    days_overdue = (as_of - bill.due_date).days - grace_days
    if days_overdue <= 0:
        return ev(BillState.NOT_YET_DUE)
    if paid > 0:
        return ev(BillState.PARTIALLY_PAID_OVERDUE, days=days_overdue)
    return ev(BillState.OVERDUE, days=days_overdue)


def current_bill(
    bills: list[BillingRecord],
    payments: list[Payment],
    as_of: date,
    grace_days: int = 0,
    lookback_months: int = 3,
) -> BillEvaluation | None:
    """Pick the bill that determines the customer's billing status.

    Among bills issued in the last `lookback_months` months (and on/before as_of), the most
    severe state wins (conflict > dispute > overdue > not yet due > paid); among overdue bills,
    the oldest (most days overdue); otherwise the latest. None means NO_BILL.
    """
    cutoff_idx = as_of.year * 12 + as_of.month - 1 - lookback_months
    recent = [
        b for b in bills
        if b.issue_date <= as_of and b.issue_date.year * 12 + b.issue_date.month - 1 >= cutoff_idx
    ]  # fmt: skip
    if not recent:
        return None
    evals = [derive_bill_state(b, payments, as_of, grace_days) for b in recent]
    return max(
        evals,
        key=lambda e: (_SEVERITY[e.state], e.days_overdue or 0, e.bill.billing_period),
    )
