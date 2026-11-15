"""BillingPolicyEngine: bill states, stage boundaries, duplicates, leakage (§6.2-6.3)."""

from datetime import date

import pytest

from app.policy import billing as b
from app.policy.billing import decide_billing
from app.policy.config import load_billing_config
from app.schemas.enums import BillState
from tests.unit.policy.policy_factories import AS_OF, bill, comm, days_ago, overdue_bill, payment

CFG = load_billing_config()
NO_SKIP_OFF = CFG.model_copy(update={"no_stage_skipping": False})


def decide(bills, payments=(), history=(), cfg=CFG):
    return decide_billing(bills, payments, history, cfg, AS_OF)


# --------------------------------------------------------------------------- states


def test_no_bill():
    d = decide([])
    assert d.state is BillState.NO_BILL and not d.reminder_allowed and not d.escalate


def test_bill_issued_after_as_of_is_ignored():
    d = decide([bill(issue_date=days_ago(-1), due_date=days_ago(-15))])
    assert d.state is BillState.NO_BILL


def test_fully_paid():
    d = decide([bill(status="PAID")], [payment(59900)])
    assert d.state is BillState.PAID and not d.reminder_allowed


def test_waived_counts_as_paid():
    assert decide([overdue_bill(20, status="WAIVED")]).state is BillState.PAID


def test_not_yet_due():
    d = decide([bill(due_date=days_ago(-5))])
    assert d.state is BillState.NOT_YET_DUE and not d.reminder_allowed
    assert d.outstanding_minor == 59900


def test_due_today_is_not_overdue():
    assert decide([overdue_bill(0)]).state is BillState.NOT_YET_DUE


def test_grace_days_delay_overdue():
    cfg = CFG.model_copy(update={"grace_days": 3})
    assert decide([overdue_bill(2)], cfg=cfg).state is BillState.NOT_YET_DUE
    d = decide([overdue_bill(5)], cfg=cfg)
    assert d.state is BillState.OVERDUE and d.days_overdue == 2


def test_overdue_stage1_with_exact_verified_facts():
    """Demo C0005: ₹599 due 10 Nov, unpaid, 5 days overdue, no prior reminders."""
    d = decide([bill()])
    assert d.state is BillState.OVERDUE
    assert d.reminder_allowed and d.stage == 1 and not d.escalate
    assert d.bill_id == "B-C0005-2026-10"
    assert d.verified_facts == {
        "bill_period": "October 2026",
        "amount_due": "₹599.00",
        "original_amount": "₹599.00",
        "due_date": "10 Nov 2026",
        "days_overdue": "5",
        "support_path": CFG.support_path,
    }
    assert "BILL_OVERDUE_DAYS:5" in d.reason_codes and "BILL_STAGE:1" in d.reason_codes


def test_partially_paid_overdue_uses_outstanding_amount():
    d = decide([overdue_bill(5, status="PARTIALLY_PAID")], [payment(30000)])
    assert d.state is BillState.PARTIALLY_PAID_OVERDUE
    assert d.outstanding_minor == 29900
    assert d.verified_facts["amount_due"] == "₹299.00"
    assert d.verified_facts["original_amount"] == "₹599.00"
    assert b.BILL_PARTIAL_PAYMENT in d.reason_codes


# --------------------------------------------------------------------------- escalations


def test_open_dispute_escalates_without_reminder():
    d = decide([overdue_bill(25, dispute_status="OPEN")])
    assert d.state is BillState.DISPUTED and d.escalate and not d.reminder_allowed
    assert d.reason_codes == [b.BILL_DISPUTED]


def test_resolved_dispute_does_not_block():
    assert decide([overdue_bill(5, dispute_status="RESOLVED")]).reminder_allowed


def test_missing_due_date_is_data_conflict():
    d = decide([bill(due_date=None)])
    assert d.state is BillState.DATA_CONFLICT and d.escalate and not d.reminder_allowed
    assert d.reason_codes == [b.BILL_DATA_MISSING]


@pytest.mark.parametrize(
    ("status", "paid", "code"),
    [
        ("PAID", [30000], b.BILL_CONFLICT_STATUS_PAYMENT),  # C0010 variant
        ("PAID", [], b.BILL_CONFLICT_STATUS_PAYMENT),
        ("UNPAID", [59900], b.BILL_CONFLICT_STATUS_PAYMENT),
        ("UNPAID", [40000, 30000], b.BILL_CONFLICT_OVERPAYMENT),
        ("PAID", [70000], b.BILL_CONFLICT_OVERPAYMENT),
    ],
)
def test_contradictory_data_escalates(status, paid, code):
    pays = [payment(a, pid=f"P-{i}") for i, a in enumerate(paid)]
    d = decide([overdue_bill(5, status=status)], pays)
    assert d.state is BillState.DATA_CONFLICT and d.escalate and not d.reminder_allowed
    assert d.reason_codes == [code]


# --------------------------------------------------------------------------- stages


@pytest.mark.parametrize(
    ("days", "stage"),
    [(1, 1), (10, 1), (11, 2), (20, 2), (21, 3), (60, 3)],
)
def test_stage_boundaries(days, stage):
    d = decide([overdue_bill(days)], cfg=NO_SKIP_OFF)
    assert d.reminder_allowed and d.stage == stage


def test_beyond_last_stage_escalates():
    d = decide([overdue_bill(61)])
    assert d.state is BillState.OVERDUE and d.escalate and not d.reminder_allowed
    assert b.BILL_BEYOND_STAGES in d.reason_codes


def test_no_stage_skipping_sends_next_stage_due():
    """25 days overdue would be stage 3 by days, but only stage 1 was ever sent -> stage 2."""
    d = decide([overdue_bill(25)], history=[comm(10, stage=1)])
    assert d.reminder_allowed and d.stage == 2


def test_first_reminder_is_stage1_even_when_very_late():
    assert decide([overdue_bill(30)]).stage == 1


def test_demo_c0006_stage3_after_two_reminders():
    """₹749 due 20 Oct, 26 days overdue, stage 1 sent 22 days ago, stage 2 sent 9 days ago."""
    d = decide(
        [overdue_bill(26, amount_due_minor=74900)],
        history=[comm(22, stage=1), comm(9, stage=2)],
    )
    assert d.reminder_allowed and d.stage == 3
    assert d.verified_facts["amount_due"] == "₹749.00"


def test_stage_never_exceeds_max_stage():
    d = decide([overdue_bill(40)], history=[comm(30, stage=3), comm(20, stage=3)])
    assert d.stage == 3


# --------------------------------------------------------------------------- duplicates


def test_reminder_within_gap_is_blocked():
    d = decide([overdue_bill(12)], history=[comm(3, stage=1)])
    assert d.state is BillState.OVERDUE and not d.reminder_allowed and not d.escalate
    assert b.BILL_REMINDER_TOO_RECENT in d.reason_codes


def test_reminder_exactly_at_gap_is_allowed():
    d = decide([overdue_bill(12)], history=[comm(7, stage=1)])
    assert d.reminder_allowed and d.stage == 2


def test_reminder_for_another_bill_does_not_count():
    d = decide([overdue_bill(12)], history=[comm(2, stage=1, bill_id="B-OTHER")])
    assert d.reminder_allowed and d.stage == 1


def test_specific_stage_objective_names_count_as_reminders():
    d = decide(
        [overdue_bill(12)], history=[comm(2, objective="BILLING_REMINDER_COURTEOUS", stage=1)]
    )
    assert not d.reminder_allowed


# --------------------------------------------------------------------------- leakage + selection


def test_payment_after_as_of_is_ignored():
    d = decide([bill()], [payment(59900, paid=days_ago(-2))])
    assert d.state is BillState.OVERDUE


def test_reminder_after_as_of_is_ignored():
    d = decide([overdue_bill(12)], history=[comm(-1, stage=1)])
    assert d.reminder_allowed and d.stage == 1


def test_latest_unsettled_bill_is_selected():
    sep = bill(
        bill_id="B-SEP",
        billing_period="2026-09",
        issue_date=days_ago(50),
        due_date=days_ago(35),
        status="PAID",
    )
    oct_ = bill(bill_id="B-OCT")
    d = decide([sep, oct_], [payment(59900, bill_id="B-SEP", paid=days_ago(40))])
    assert d.bill_id == "B-OCT" and d.state is BillState.OVERDUE


def test_latest_bill_used_when_all_settled():
    sep = bill(bill_id="B-SEP", billing_period="2026-09", status="PAID")
    oct_ = bill(bill_id="B-OCT", status="PAID")
    pays = [payment(59900, bill_id="B-SEP", pid="P1"), payment(59900, bill_id="B-OCT", pid="P2")]
    d = decide([oct_, sep], pays)
    assert d.state is BillState.PAID and d.bill_id == "B-OCT"


def test_partially_paid_status_without_payments_is_plain_overdue():
    """Shared rule with M1 (app/features/billing_state.py): status text is not trusted over
    payments; no payment received means OVERDUE, not a data conflict."""
    d = decide([overdue_bill(5, status="PARTIALLY_PAID")])
    assert d.state is BillState.OVERDUE and d.reminder_allowed


def test_demo_c0006_older_overdue_bill_wins_over_newer_bill_not_yet_due():
    """Regression: October is 26 days overdue, November not due yet -> remind about October."""
    oct_ = overdue_bill(26, bill_id="B-OCT", billing_period="2026-10", amount_due_minor=74900)
    nov = bill(
        bill_id="B-NOV",
        billing_period="2026-11",
        issue_date=days_ago(10),
        due_date=days_ago(-5),
        amount_due_minor=74900,
    )
    d = decide(
        [oct_, nov], history=[comm(22, stage=1, bill_id="B-OCT"), comm(9, stage=2, bill_id="B-OCT")]
    )
    assert d.bill_id == "B-OCT" and d.state is BillState.OVERDUE
    assert d.reminder_allowed and d.stage == 3


def test_bills_older_than_lookback_are_ignored():
    old = bill(billing_period="2026-06", issue_date=date(2026, 6, 1), due_date=date(2026, 6, 15))
    assert decide([old]).state is BillState.NO_BILL
