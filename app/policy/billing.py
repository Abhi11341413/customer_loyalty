"""BillingPolicyEngine (FR-06): bill state, reminder stage, verified facts.

Owner: M2. Deterministic, no LLM import (CLAUDE.md §6).

Which bill counts, and its state (§6.2), come from M1's ``app.features.billing_state``
(``current_bill``): one implementation, so the classification flag PAYMENT_REMINDER and the
reminder decision can never disagree. This module adds the policy on top: escalation,
reminder stages, the duplicate-reminder gap and the verified facts the LLM may use.

Golden rule for missing or contradictory data: never guess, never message — escalate
with a reason code.
"""

from collections.abc import Iterable
from datetime import date

from app.features.billing_state import BillEvaluation, current_bill
from app.policy.config import BillingConfig
from app.policy.formatting import format_date, format_money, format_period
from app.policy.history import BILLING_REMINDER_GROUP, days_since, history_as_of, objective_group
from app.schemas.customer import BillingRecord, CommunicationRecord, Payment
from app.schemas.enums import BillConflictType, BillState
from app.schemas.policy import BillingDecision

# Reason codes
BILL_DATA_MISSING = "BILL_DATA_MISSING"
BILL_DISPUTED = "BILL_DISPUTED"
BILL_CONFLICT_STATUS_PAYMENT = "BILL_DATA_CONFLICT:STATUS_PAYMENT_MISMATCH"
BILL_CONFLICT_OVERPAYMENT = "BILL_DATA_CONFLICT:OVERPAYMENT"
BILL_BEYOND_STAGES = "BILL_BEYOND_AUTOMATED_STAGES"
BILL_REMINDER_TOO_RECENT = "BILL_REMINDER_TOO_RECENT"
BILL_PARTIAL_PAYMENT = "BILL_PARTIAL_PAYMENT"

_CONFLICT_CODES = {
    BillConflictType.MISSING_FIELD: BILL_DATA_MISSING,
    BillConflictType.STATUS_PAYMENT_MISMATCH: BILL_CONFLICT_STATUS_PAYMENT,
    BillConflictType.OVERPAYMENT: BILL_CONFLICT_OVERPAYMENT,
}
_OVERDUE = (BillState.OVERDUE, BillState.PARTIALLY_PAID_OVERDUE)


def _escalation(ev: BillEvaluation) -> BillingDecision | None:
    if ev.state is BillState.DATA_CONFLICT:
        code = _CONFLICT_CODES.get(ev.conflict, BILL_DATA_MISSING)  # type: ignore[arg-type]
        return BillingDecision(
            state=ev.state, reminder_allowed=False, escalate=True,
            bill_id=ev.bill.bill_id, reason_codes=[code],
        )  # fmt: skip
    if ev.state is BillState.DISPUTED:
        return BillingDecision(
            state=ev.state, reminder_allowed=False, escalate=True,
            bill_id=ev.bill.bill_id, reason_codes=[BILL_DISPUTED],
        )  # fmt: skip
    return None


def decide_billing(
    bills: Iterable[BillingRecord],
    payments: Iterable[Payment],
    history: Iterable[CommunicationRecord],
    cfg: BillingConfig,
    as_of: date,
) -> BillingDecision:
    """Derive the bill state and whether (and at which stage) a reminder may be drafted."""
    ev = current_bill(list(bills), list(payments), as_of, cfg.grace_days, cfg.bill_lookback_months)
    if ev is None:
        return BillingDecision(state=BillState.NO_BILL, reminder_allowed=False)

    escalation = _escalation(ev)
    if escalation is not None:
        return escalation

    bill = ev.bill
    if ev.state not in _OVERDUE:  # PAID / NOT_YET_DUE
        outstanding = ev.outstanding_minor if ev.state is BillState.NOT_YET_DUE else None
        return BillingDecision(
            state=ev.state, reminder_allowed=False, bill_id=bill.bill_id,
            outstanding_minor=outstanding,
        )  # fmt: skip

    days_overdue = ev.days_overdue or 0
    reasons = [f"BILL_OVERDUE_DAYS:{days_overdue}"]
    if ev.state is BillState.PARTIALLY_PAID_OVERDUE:
        reasons.append(BILL_PARTIAL_PAYMENT)
    common = {
        "state": ev.state,
        "bill_id": bill.bill_id,
        "days_overdue": days_overdue,
        "outstanding_minor": ev.outstanding_minor,
    }

    stage_by_days = cfg.stage_for(days_overdue)
    if stage_by_days is None:
        return BillingDecision(
            reminder_allowed=False,
            escalate=True,
            reason_codes=[*reasons, BILL_BEYOND_STAGES],
            **common,
        )

    sent = [
        h
        for h in history_as_of(history, as_of)
        if h.related_bill_id == bill.bill_id
        and objective_group(h.objective) == BILLING_REMINDER_GROUP
    ]
    last = max(sent, key=lambda h: h.sent_at, default=None)
    if last is not None and days_since(last, as_of) < cfg.min_days_between_reminders:
        return BillingDecision(
            reminder_allowed=False, reason_codes=[*reasons, BILL_REMINDER_TOO_RECENT], **common
        )

    highest_sent = max((h.reminder_stage or 0 for h in sent), default=0)
    stage = min(stage_by_days, highest_sent + 1) if cfg.no_stage_skipping else stage_by_days
    stage = min(stage, cfg.max_stage)

    assert bill.due_date is not None  # guaranteed: missing due date is a DATA_CONFLICT above
    return BillingDecision(
        reminder_allowed=True,
        stage=stage,
        verified_facts={
            "bill_period": format_period(bill.billing_period),
            "amount_due": format_money(ev.outstanding_minor, bill.currency),
            "original_amount": format_money(bill.amount_due_minor, bill.currency),
            "due_date": format_date(bill.due_date),
            "days_overdue": str(days_overdue),
            "support_path": cfg.support_path,
        },
        reason_codes=[*reasons, f"BILL_STAGE:{stage}"],
        **common,
    )
