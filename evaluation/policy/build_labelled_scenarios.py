"""Build M2's half of evaluation/datasets/labelled_scenarios.jsonl (CLAUDE.md §14.7).

Owner: M2. Labelled by M2 — not by M1, the classification-rule author — so the evaluation
is not circular. M3 labels the other half (ids C02xx); this script only replaces lines with
"labelled_by": "M2" and keeps everything else in the file.

Each scenario is a short spec (what kind of customer) plus HAND-WRITTEN expected labels,
derived from the written definitions in CLAUDE.md §5.2 (segments), §6-7 (billing, offers,
strategy) and the policy YAMLs — never from engine output. The spec is expanded into the
same row format as data/seed/demo_customers.json, so M1's
`python evaluation/classification/run.py --labelled` can load it unchanged.

    python evaluation/policy/build_labelled_scenarios.py
"""

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evaluation" / "datasets" / "labelled_scenarios.jsonl"
AS_OF = date(2026, 11, 15)
PRICES = {"PL-POST-499": 49900, "PL-POST-599": 59900, "PL-PRE-299": 29900}
# The 6 full months before the as-of month, used by the activity rules (A-01).
LAST6 = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]


def ago(n: int) -> date:
    return AS_OF - timedelta(days=n)


def month_seq(start: date, end_month: str) -> list[str]:
    y, m = start.year, start.month
    out = []
    while f"{y:04d}-{m:02d}" <= end_month:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


@dataclass
class Spec:
    cid: str
    category: str  # positive | negative | borderline | edge
    desc: str
    expected: dict
    since: date = date(2026, 3, 10)
    plan: str = "PL-POST-599"
    first_name: str = "Alex"
    #: usage events per month in LAST6 order (None = steady 30)
    usage: list[int] | None = None
    #: days since the last activity (None = active this month)
    last_activity_ago: int | None = None
    late_periods: list[str] = field(default_factory=list)  # paid, but after the due date
    overdue_days: int | None = None  # one unpaid bill this many days overdue
    overdue_paid: int = 0  # partial payment on that bill
    overdue_status: str = "UNPAID"
    overdue_dispute: str = "NONE"
    prefs: dict = field(default_factory=dict)
    #: (days ago, category, objective, reminder stage, about the overdue bill?, offer id)
    comms: list[tuple] = field(default_factory=list)
    redemptions: list[tuple[str, int]] = field(default_factory=list)  # (offer id, days ago)


def build(s: Spec) -> dict:
    cid = s.cid
    price = PRICES[s.plan]
    rows: dict = {
        "customer": {
            "customer_id": cid, "first_name": s.first_name,
            "email": f"{s.first_name.lower()}.{cid.lower()}@example.test",
            "customer_since": s.since.isoformat(), "account_status": "ACTIVE",
            "is_synthetic": 1, "created_at": "2026-11-01T00:00:00Z",
        },
        "contact_preferences": {
            "customer_id": cid, "email_service_consent": 1, "email_marketing_consent": 1,
            "email_opt_out": 0, "preferred_channel": "EMAIL", "do_not_contact_until": "",
            "consent_updated_at": f"{s.since.isoformat()}T00:00:00Z", **s.prefs,
        },
        "customer_plans": [{
            "customer_plan_id": f"CP-{cid}-1", "customer_id": cid, "plan_id": s.plan,
            "start_date": s.since.isoformat(), "end_date": "", "status": "ACTIVE",
        }],
        "customer_activity_monthly": [], "billing_records": [], "payments": [],
        "offer_redemptions": [], "communication_history": [],
    }  # fmt: skip

    # --- activity: one row per month since joining, up to the (partial) as-of month
    usage = dict(zip(LAST6, s.usage or [30] * 6, strict=True))
    last_seen = ago(s.last_activity_ago) if s.last_activity_ago is not None else ago(3)
    for month in month_seq(s.since, "2026-11"):
        events = usage.get(month, 30 if month < LAST6[0] else 15)
        month_end = date.fromisoformat(f"{month}-28")
        if month_end > last_seen and month[:7] > last_seen.strftime("%Y-%m"):
            events = 0
        last = min(month_end, last_seen) if events else None
        rows["customer_activity_monthly"].append({
            "customer_id": cid, "month": month, "active_days": events // 2,
            "usage_events": events, "last_activity_date": last.isoformat() if last else "",
        })  # fmt: skip

    # --- bills: monthly, issued on the 5th, due on the 20th, paid on the 17th
    overdue_due = ago(s.overdue_days) if s.overdue_days is not None else None
    overdue_period = (overdue_due - timedelta(days=15)).strftime("%Y-%m") if overdue_due else None
    first_bill = date(s.since.year, s.since.month, 1)
    for period in month_seq(first_bill, "2026-11"):
        bill_id = f"B-{cid}-{period}"
        if period == overdue_period:
            due = overdue_due
            issue = due - timedelta(days=15)
            status, dispute, paid = s.overdue_status, s.overdue_dispute, s.overdue_paid
            paid_on = ago(max(s.overdue_days - 3, 1)) if paid else None
        else:
            issue, due = date.fromisoformat(f"{period}-05"), date.fromisoformat(f"{period}-20")
            if issue > AS_OF:
                continue
            if due >= AS_OF:  # current bill, not yet due
                status, dispute, paid, paid_on = "UNPAID", "NONE", 0, None
            else:
                late = period in s.late_periods
                paid_on = due + timedelta(days=6) if late else due - timedelta(days=3)
                status, dispute, paid = "PAID", "NONE", price
        rows["billing_records"].append({
            "bill_id": bill_id, "customer_id": cid, "billing_period": period,
            "issue_date": issue.isoformat(), "due_date": due.isoformat(),
            "amount_due_minor": price, "currency": "INR", "status": status,
            "dispute_status": dispute,
        })  # fmt: skip
        if paid:
            rows["payments"].append({
                "payment_id": f"P-{cid}-{period}-1", "bill_id": bill_id,
                "paid_date": paid_on.isoformat(), "amount_paid_minor": paid,
            })  # fmt: skip

    for i, (n_ago, category, objective, stage, about_overdue, offer_id) in enumerate(s.comms, 1):
        rows["communication_history"].append({
            "comm_id": f"CM-{cid}-{i}", "customer_id": cid, "channel": "EMAIL",
            "reminder_stage": stage or "",
            "related_bill_id": f"B-{cid}-{overdue_period}" if about_overdue else "",
            "offer_id": offer_id or "", "draft_id": "", "source": "HISTORICAL_SEED",
            "sent_at": f"{ago(n_ago).isoformat()}T09:00:00Z", "category": category,
            "objective": objective,
        })  # fmt: skip
    for i, (offer_id, n_ago) in enumerate(s.redemptions, 1):
        rows["offer_redemptions"].append({
            "redemption_id": f"R-{cid}-{i}", "offer_id": offer_id, "customer_id": cid,
            "redeemed_at": f"{ago(n_ago).isoformat()}T10:00:00Z",
        })  # fmt: skip

    return {
        "id": cid, "labelled_by": "M2", "category": s.category, "description": s.desc,
        "input": rows, "expected": s.expected,
    }  # fmt: skip


def exp(
    engagement, flags=(), objective="", offer=None, bill="NOT_YET_DUE", terminal="PENDING_REVIEW"
):
    """Labels. Default bill state NOT_YET_DUE: every scenario has a November bill issued on
    5 Nov and due 20 Nov, which outranks the paid history (§6.2)."""
    segs = [engagement, *flags]
    return {"engagement": engagement, "segments": segs, "objective": objective,
            "offer_id": offer, "billing_state": bill, "terminal_status": terminal}  # fmt: skip


C, L, P = "CONSISTENT", "LOYALTY_CANDIDATE", "PAYMENT_REMINDER"
REMINDER = ("SERVICE", "BILLING_REMINDER")
LOYAL_SINCE = date(2024, 11, 1)  # 24 months

SPECS = [
    # ---------------------------------------------------------------- positive
    Spec(
        "C0101",
        "positive",
        "Consistent, 8 months tenure, all bills on time",
        exp(C, objective="APPRECIATION"),
    ),
    Spec(
        "C0102",
        "positive",
        "Loyal: 24 months, every bill on time, eligible plan",
        exp(C, [L], "LOYALTY_REWARD", "OFF-LOY-200"),
        since=LOYAL_SINCE,
    ),
    Spec(
        "C0103",
        "positive",
        "Loyal but on a prepaid plan the reward does not cover -> appreciation",
        exp(C, [L], "APPRECIATION"),
        since=LOYAL_SINCE,
        plan="PL-PRE-299",
    ),
    Spec(
        "C0104",
        "positive",
        "Declining: about 40 events/month falling to about 13",
        exp("DECLINING_ACTIVITY", objective="REENGAGEMENT", offer="OFF-RE-5GB"),
        usage=[40, 42, 38, 14, 12, 13],
    ),
    Spec(
        "C0105",
        "positive",
        "Dormant: no activity for 90 days, plan still active",
        exp("DORMANT", objective="WINBACK", offer="OFF-RE-5GB"),
        usage=[30, 30, 30, 30, 0, 0],
        last_activity_ago=90,
    ),
    Spec(
        "C0106",
        "positive",
        "Consistent customer, bill 3 days overdue, no reminder yet",
        exp(C, [P], "BILLING_REMINDER_COURTEOUS", bill="OVERDUE"),
        overdue_days=3,
    ),
    Spec(
        "C0107",
        "positive",
        "15 days overdue, stage 1 sent 10 days ago -> stage 2",
        exp(C, [P], "BILLING_REMINDER_FOLLOWUP", bill="OVERDUE"),
        overdue_days=15,
        comms=[(10, *REMINDER, 1, True, None)],
    ),
    Spec(
        "C0108",
        "positive",
        "30 days overdue, stages 1 and 2 already sent -> stage 3",
        exp(C, [P], "BILLING_REMINDER_FIRM", bill="OVERDUE"),
        overdue_days=30,
        comms=[(25, *REMINDER, 1, True, None), (12, *REMINDER, 2, True, None)],
    ),
    # ---------------------------------------------------------------- negative
    Spec(
        "C0109",
        "negative",
        "Paid last bill one day late -> paid, must NOT get a reminder",
        exp(C, objective="APPRECIATION"),
        late_periods=["2026-10"],
    ),
    Spec(
        "C0110",
        "negative",
        "New customer, joined 2 months ago -> not enough data",
        exp("INSUFFICIENT_DATA", objective="ESCALATE", bill="NOT_YET_DUE", terminal="ESCALATED"),
        since=date(2026, 9, 20),
    ),
    Spec(
        "C0111",
        "negative",
        "Irregular usage, active in only 3 of 6 months -> no targeted outreach",
        exp("STANDARD", objective="NO_CONTACT", terminal="REFUSED"),
        usage=[5, 40, 2, 35, 3, 30],
    ),
    Spec(
        "C0112",
        "negative",
        "Loyal-looking but one late payment in the last 6 months",
        exp(C, objective="APPRECIATION"),
        since=LOYAL_SINCE,
        late_periods=["2026-08"],
    ),
    # ---------------------------------------------------------------- borderline
    Spec(
        "C0113",
        "borderline",
        "Tenure exactly 12 months, perfect payments -> loyalty",
        exp(C, [L], "LOYALTY_REWARD", "OFF-LOY-200"),
        since=date(2025, 11, 10),
    ),
    Spec(
        "C0114",
        "borderline",
        "Tenure 11 months, perfect payments -> not yet loyalty",
        exp(C, objective="APPRECIATION"),
        since=date(2025, 12, 10),
    ),
    Spec(
        "C0115",
        "borderline",
        "Exactly 10 days overdue -> still stage 1",
        exp(C, [P], "BILLING_REMINDER_COURTEOUS", bill="OVERDUE"),
        overdue_days=10,
    ),
    Spec(
        "C0116",
        "borderline",
        "61 days overdue -> beyond automated reminders, escalate",
        exp(C, [P], "ESCALATE", bill="OVERDUE", terminal="ESCALATED"),
        overdue_days=61,
        comms=[
            (40, *REMINDER, 1, True, None),
            (30, *REMINDER, 2, True, None),
            (15, *REMINDER, 3, True, None),
        ],
    ),
    # ---------------------------------------------------------------- edge
    Spec(
        "C0117",
        "edge",
        "Open dispute on an overdue bill -> escalate, no reminder flag",
        exp(C, objective="ESCALATE", bill="DISPUTED", terminal="ESCALATED"),
        overdue_days=20,
        overdue_dispute="OPEN",
    ),
    Spec(
        "C0118",
        "edge",
        "Bill marked PAID but only half paid -> data conflict",
        exp(C, objective="ESCALATE", bill="DATA_CONFLICT", terminal="ESCALATED"),
        overdue_days=25,
        overdue_status="PAID",
        overdue_paid=29950,
    ),
    Spec(
        "C0119",
        "edge",
        "Overdue but opted out of all email -> refused",
        exp(C, [P], "NO_CONTACT_BY_POLICY", bill="OVERDUE", terminal="REFUSED"),
        overdue_days=5,
        prefs={"email_opt_out": 1, "email_service_consent": 0, "email_marketing_consent": 0},
    ),
    Spec(
        "C0120",
        "edge",
        "Overdue, marketing consent only (no service consent) -> refused",
        exp(C, [P], "NO_CONTACT_BY_POLICY", bill="OVERDUE", terminal="REFUSED"),
        overdue_days=5,
        prefs={"email_service_consent": 0},
    ),
    Spec(
        "C0121",
        "edge",
        "12 days overdue but a reminder went out 3 days ago -> wait",
        exp(C, [P], "NO_CONTACT", bill="OVERDUE", terminal="REFUSED"),
        overdue_days=12,
        comms=[(3, *REMINDER, 1, True, None)],
    ),
    Spec(
        "C0122",
        "edge",
        "Declining, but already redeemed the bonus-data offer -> no offer",
        exp("DECLINING_ACTIVITY", objective="REENGAGEMENT"),
        usage=[40, 42, 38, 14, 12, 13],
        redemptions=[("OFF-RE-5GB", 60)],
    ),
    Spec(
        "C0123",
        "edge",
        "Consistent, but a marketing email went out 5 days ago -> refused",
        exp(C, objective="NO_CONTACT_BY_POLICY", terminal="REFUSED"),
        comms=[(5, "MARKETING", "APPRECIATION", None, False, None)],
    ),
]


def main() -> None:
    others = []
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if line.strip() and json.loads(line).get("labelled_by") != "M2":
                others.append(line)
    mine = [json.dumps(build(s), ensure_ascii=False) for s in SPECS]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(others + mine) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(mine)} M2 scenarios (+{len(others)} from others) to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
