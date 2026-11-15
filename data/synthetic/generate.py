"""Archetype-based synthetic data generator (deterministic with --seed).

Owner: M1.

Usage (from the project root):
    python data/synthetic/generate.py --demo         # data/seed/demo_customers.json
    python data/synthetic/generate.py --split dev    # 200 customers -> data/synthetic/dev/*.csv
    python data/synthetic/generate.py --split eval   # 500 customers, other seed, git-ignored

All data is synthetic. Names are drawn uniformly at random, independent of archetype, so a name
can never correlate with treatment. Emails use the reserved non-routable domain example.test.

`labels.csv` records the INTENDED truth per customer (archetype + borderline parameter). It is
kept separate from anything the rules compute. Thresholds used to label borderline cases mirror
config/policies/segments.yaml (ASSUMPTIONS).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from app.data import models

AS_OF = date(2026, 11, 15)
ROOT = Path(__file__).resolve().parent
DEMO_PATH = ROOT.parent / "seed" / "demo_customers.json"
CREATED_AT = "2026-11-01T00:00:00Z"

FIRST_NAMES = [
    "Asha", "Ravi", "Mei", "Daniel", "Fatima", "Kwame", "Sofia", "Arjun", "Yuki", "Liam",
    "Amara", "Diego", "Priya", "Omar", "Elena", "Chen", "Aisha", "Lucas", "Nadia", "Tomas",
    "Zara", "Kenji", "Ines", "Samuel", "Leila", "Mateo", "Hana", "Ibrahim", "Grace", "Nikhil",
    "Ana", "Felix", "Noor", "Rahul", "Chloe", "Tariq", "Mia", "Jonas", "Divya", "Kofi",
]  # fmt: skip

PLANS = {  # plan_id -> monthly bill (minor units)
    "PL-POST-499": 49900,
    "PL-POST-599": 59900,
    "PL-POST-749": 74900,
    "PL-BB-799": 79900,
}

SPLITS = {"dev": (200, 42, 1001), "eval": (500, 1337, 5001)}

ARCHETYPE_WEIGHTS = {
    "consistent": 18, "loyal": 15, "declining": 12, "dormant": 10, "overdue_s1": 8,
    "overdue_s3": 6, "partial_payer": 5, "disputed": 4, "new_customer": 6, "irregular": 8,
    "contradictory": 5, "opted_out": 3,
}  # fmt: skip
BORDERLINE_SHARE = 0.15


# --------------------------------------------------------------------------- helpers
def month_start(d: date, offset: int = 0) -> date:
    idx = d.year * 12 + (d.month - 1) + offset
    return date(idx // 12, idx % 12 + 1, 1)


def months_between(a: date, b: date) -> int:
    n = (b.year - a.year) * 12 + (b.month - a.month)
    return n - 1 if b.day < a.day else n


def since_for_tenure(tenure: int, day: int = 1) -> date:
    m = month_start(AS_OF, -tenure)
    return date(m.year, m.month, min(day, AS_OF.day, 28))


def iso(d: date | None) -> str:
    return d.isoformat() if d else ""


# --------------------------------------------------------------------------- spec
@dataclass
class Spec:
    """Declarative description of one customer; build_rows() turns it into table rows."""

    customer_id: str
    first_name: str
    since: date
    plan_id: str = "PL-POST-499"
    usage: list[int] = field(default_factory=lambda: [30] * 6)  # 6 full months, oldest first
    last_activity: date | None = None  # default: AS_OF - 2 days
    issue_day: int = 27
    due_days: int = 14
    pay_days_before_due: int = 3
    bill_overrides: dict[str, str] = field(default_factory=dict)  # period -> kind
    unpaid_from: str | None = None  # every bill from this period on is unpaid
    prefs: dict = field(default_factory=dict)
    comms: list[dict] = field(default_factory=list)
    account_status: str = "ACTIVE"
    scenario: str = ""
    expected: dict = field(default_factory=dict)

    @property
    def bill_amount(self) -> int:
        return PLANS.get(self.plan_id, 49900)


def build_rows(s: Spec, rng: random.Random | None = None) -> dict[str, list[dict]]:
    cid = s.customer_id
    last_act = s.last_activity or (AS_OF - timedelta(days=2))
    rows: dict[str, list[dict]] = {k: [] for k in (
        "customers", "customer_contact_preferences", "customer_plans",
        "customer_activity_monthly", "billing_records", "payments", "communication_history",
    )}  # fmt: skip

    rows["customers"].append(
        {
            "customer_id": cid,
            "first_name": s.first_name,
            "email": f"{s.first_name.lower()}.{cid.lower()}@example.test",
            "customer_since": iso(s.since),
            "account_status": s.account_status,
            "is_synthetic": 1,
            "created_at": CREATED_AT,
        }
    )
    prefs = {
        "customer_id": cid, "email_service_consent": 1, "email_marketing_consent": 1,
        "email_opt_out": 0, "preferred_channel": "EMAIL", "do_not_contact_until": "",
        "consent_updated_at": f"{iso(s.since)}T00:00:00Z",
    }  # fmt: skip
    prefs.update(s.prefs)
    rows["customer_contact_preferences"].append(prefs)
    rows["customer_plans"].append({
        "customer_plan_id": f"CP-{cid}-1", "customer_id": cid, "plan_id": s.plan_id,
        "start_date": iso(s.since), "end_date": "", "status": "ACTIVE",
    })  # fmt: skip

    # Activity: since-month .. AS_OF month (max 13 rows). k = months before AS_OF's month.
    first = max(month_start(s.since), month_start(AS_OF, -12))
    m = first
    while m <= month_start(AS_OF):
        k = (AS_OF.year - m.year) * 12 + (AS_OF.month - m.month)
        if k == 0:
            usage = round(s.usage[-1] * AS_OF.day / 30)
        elif k <= 6:
            usage = s.usage[6 - k]
        else:
            usage = s.usage[0]
        if rng is not None and k > 6:
            usage = max(0, round(usage * rng.uniform(0.9, 1.1)))
        last_date: date | None
        if m > month_start(last_act):
            usage, last_date = 0, None
        elif m == month_start(last_act):
            usage, last_date = max(usage, 1), last_act
        else:
            last_date = date(m.year, m.month, 28) if usage > 0 else None
        if m == month_start(s.since) and last_date and last_date < s.since:
            last_date = s.since
        cap = 28
        if last_date and m == month_start(last_date):
            cap = last_date.day - (s.since.day - 1 if m == month_start(s.since) else 0)
        active_days = 0 if usage == 0 else max(1, min(round(usage * 0.5), max(cap, 1)))
        rows["customer_activity_monthly"].append({
            "customer_id": cid, "month": m.strftime("%Y-%m"), "active_days": active_days,
            "usage_events": usage, "last_activity_date": iso(last_date),
        })  # fmt: skip
        m = month_start(m, 1)

    # Bills: one per period, issued on issue_day, last 14 periods with issue <= AS_OF.
    periods = []
    m = month_start(s.since)
    while m <= month_start(AS_OF):
        issue = date(m.year, m.month, min(s.issue_day, 28))
        if s.since <= issue <= AS_OF:
            periods.append((m.strftime("%Y-%m"), issue))
        m = month_start(m, 1)
    for period, issue in periods[-14:]:
        bill_id = f"B-{cid}-{period}"
        due: date | None = issue + timedelta(days=s.due_days)
        kind = s.bill_overrides.get(period, "paid")
        if s.unpaid_from and period >= s.unpaid_from and kind == "paid":
            kind = "unpaid"
        amount = s.bill_amount
        pays: list[tuple[date, int]] = []
        status, dispute = None, "NONE"
        if kind == "paid":
            when = due - timedelta(days=s.pay_days_before_due)
            if rng is not None:
                when = due - timedelta(days=rng.randint(0, 8))
            when = max(when, issue)
            if when <= AS_OF:
                pays.append((when, amount))
        elif kind.startswith("late:"):
            when = due + timedelta(days=int(kind.split(":")[1]))
            if when <= AS_OF:
                pays.append((when, amount))
        elif kind.startswith("partial:"):
            pays.append((max(issue, due - timedelta(days=2)), int(kind.split(":")[1])))
        elif kind == "disputed":
            dispute = "OPEN"
        elif kind == "missing_due":
            due = None
        elif kind.startswith("paid_status_partial:"):
            pays.append((issue + timedelta(days=3), int(kind.split(":")[1])))
            status = "PAID"
        elif kind.startswith("overpay:"):
            pays.append((issue + timedelta(days=3), amount + int(kind.split(":")[1])))
            status = "PAID"
        elif kind == "unpaid_status_but_paid":
            pays.append((issue + timedelta(days=3), amount))
            status = "UNPAID"
        elif kind == "waived":
            status = "WAIVED"
        elif kind != "unpaid":
            raise ValueError(f"unknown bill override {kind!r}")
        paid = sum(a for _, a in pays)
        if status is None:
            status = "PAID" if paid >= amount else ("PARTIALLY_PAID" if paid else "UNPAID")
        rows["billing_records"].append({
            "bill_id": bill_id, "customer_id": cid, "billing_period": period,
            "issue_date": iso(issue), "due_date": iso(due), "amount_due_minor": amount,
            "currency": "INR", "status": status, "dispute_status": dispute,
        })  # fmt: skip
        for i, (when, amt) in enumerate(pays, 1):
            rows["payments"].append({
                "payment_id": f"P-{cid}-{period}-{i}", "bill_id": bill_id,
                "paid_date": iso(when), "amount_paid_minor": amt,
            })  # fmt: skip

    for i, c in enumerate(s.comms, 1):
        row = {
            "comm_id": f"CM-{cid}-{i}", "customer_id": cid, "channel": "EMAIL",
            "reminder_stage": "", "related_bill_id": "", "offer_id": "", "draft_id": "",
            "source": "HISTORICAL_SEED",
        }  # fmt: skip
        row.update(c)
        rows["communication_history"].append(row)
    return rows


def on_time_counts(rows: dict[str, list[dict]]) -> tuple[int, int, int]:
    """(bills due in last 12m, of which paid in full on time, paid late in last 6m)."""
    lo12, lo6 = month_start(AS_OF, -12).replace(day=AS_OF.day), month_start(AS_OF, -6)
    lo6 = lo6.replace(day=AS_OF.day)
    paid: dict[str, list[tuple[date, int]]] = {}
    for p in rows["payments"]:
        paid.setdefault(p["bill_id"], []).append(
            (date.fromisoformat(p["paid_date"]), p["amount_paid_minor"])
        )
    n = ok = late6 = 0
    for b in rows["billing_records"]:
        if not b["due_date"] or b["status"] == "WAIVED":
            continue
        due = date.fromisoformat(b["due_date"])
        if not (lo12 < due <= AS_OF):
            continue
        n += 1
        by_due = sum(a for d, a in paid.get(b["bill_id"], []) if d <= due)
        if by_due >= b["amount_due_minor"]:
            ok += 1
        elif due > lo6 and sum(a for _, a in paid.get(b["bill_id"], [])) >= b["amount_due_minor"]:
            late6 += 1
    return n, ok, late6


# --------------------------------------------------------------------------- demo set
def demo_specs() -> list[Spec]:
    """The 10 fixed demo customers. As of 2026-11-15. Values are synthetic."""
    return [
        Spec("C0001", "Mei", date(2026, 3, 10), "PL-POST-599", [28, 30, 29, 31, 30, 31],
             scenario="Consistent customer",
             expected={"engagement": "CONSISTENT", "segments": ["CONSISTENT"]}),
        Spec("C0002", "Asha", date(2024, 4, 10), "PL-POST-499", [34, 35, 33, 36, 34, 35],
             scenario="Loyalty-reward candidate",
             comms=[{"sent_at": "2026-08-01T09:00:00Z", "category": "MARKETING",
                     "objective": "APPRECIATION"}],
             expected={"engagement": "CONSISTENT",
                       "segments": ["CONSISTENT", "LOYALTY_CANDIDATE"]}),
        Spec("C0003", "Daniel", date(2025, 3, 12), "PL-POST-499", [41, 39, 40, 15, 13, 14],
             last_activity=date(2026, 11, 9), scenario="Declining activity",
             expected={"engagement": "DECLINING_ACTIVITY", "segments": ["DECLINING_ACTIVITY"]}),
        Spec("C0004", "Fatima", date(2024, 9, 1), "PL-BB-799", [30, 32, 31, 15, 0, 0],
             last_activity=date(2026, 8, 15), scenario="Inactive / dormant",
             expected={"engagement": "DORMANT", "segments": ["DORMANT"]}),
        Spec("C0005", "Ravi", date(2026, 1, 5), "PL-POST-599", [30, 29, 31, 30, 32, 30],
             bill_overrides={"2026-10": "unpaid"}, scenario="Overdue bill - courteous",
             expected={"engagement": "CONSISTENT",
                       "segments": ["CONSISTENT", "PAYMENT_REMINDER"]}),
        Spec("C0006", "Kwame", date(2026, 1, 8), "PL-POST-749", [27, 29, 28, 30, 28, 29],
             issue_day=5, due_days=15, unpaid_from="2026-10", scenario="Overdue bill - firmer",
             comms=[
                 {"sent_at": "2026-10-24T09:00:00Z", "category": "SERVICE",
                  "objective": "BILLING_REMINDER", "reminder_stage": 1,
                  "related_bill_id": "B-C0006-2026-10"},
                 {"sent_at": "2026-11-06T09:00:00Z", "category": "SERVICE",
                  "objective": "BILLING_REMINDER", "reminder_stage": 2,
                  "related_bill_id": "B-C0006-2026-10"},
             ],
             expected={"engagement": "CONSISTENT",
                       "segments": ["CONSISTENT", "PAYMENT_REMINDER"]}),
        Spec("C0007", "Sofia", date(2023, 7, 1), "PL-POST-599", [33, 34, 32, 35, 33, 34],
             prefs={"email_service_consent": 0, "email_marketing_consent": 0,
                    "email_opt_out": 1, "preferred_channel": "NONE",
                    "consent_updated_at": "2026-09-02T10:00:00Z"},
             scenario="Refusal - opted out",
             expected={"engagement": "CONSISTENT",
                       "segments": ["CONSISTENT", "LOYALTY_CANDIDATE"]}),
        Spec("C0008", "Arjun", date(2025, 8, 3), "PL-POST-499", [45, 42, 44, 16, 15, 14],
             last_activity=date(2026, 11, 12), scenario="Refusal - unsafe LLM output",
             expected={"engagement": "DECLINING_ACTIVITY", "segments": ["DECLINING_ACTIVITY"]}),
        Spec("C0009", "Yuki", date(2024, 4, 10), "PL-POST-499", [34, 33, 35, 34, 36, 35],
             issue_day=20, due_days=14, bill_overrides={"2026-10": "unpaid"},
             scenario="Conflict - loyal + overdue",
             comms=[{"sent_at": "2026-11-05T09:00:00Z", "category": "SERVICE",
                     "objective": "BILLING_REMINDER", "reminder_stage": 1,
                     "related_bill_id": "B-C0009-2026-10"}],
             expected={"engagement": "CONSISTENT",
                       "segments": ["CONSISTENT", "LOYALTY_CANDIDATE", "PAYMENT_REMINDER"]}),
        Spec("C0010", "Liam", date(2026, 2, 2), "PL-POST-599", [31, 30, 32, 31, 30, 31],
             bill_overrides={"2026-10": "disputed"}, scenario="Escalation - disputed bill",
             expected={"engagement": "CONSISTENT", "segments": ["CONSISTENT"],
                       "reason_codes_include": ["BILL_DISPUTED"]}),
    ]  # fmt: skip


def write_demo(path: Path = DEMO_PATH) -> None:
    customers = []
    for s in demo_specs():
        rows = build_rows(s)
        customers.append({
            "scenario": s.scenario,
            "expected": s.expected,
            "customer": rows["customers"][0],
            "contact_preferences": rows["customer_contact_preferences"][0],
            **{k: v for k, v in rows.items()
               if k not in ("customers", "customer_contact_preferences")},
        })  # fmt: skip
    doc = {"as_of_date": AS_OF.isoformat(), "note": "Synthetic demo fixtures. Do not edit by "
           "hand - regenerate with: python data/synthetic/generate.py --demo",
           "customers": customers}  # fmt: skip
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(customers)} customers)")


# --------------------------------------------------------------------------- archetypes
def _flat(rng: random.Random, base: float, n: int = 6, jitter: float = 0.08) -> list[int]:
    return [max(1, round(base * rng.uniform(1 - jitter, 1 + jitter))) for _ in range(n)]


def sample(arch: str, cid: str, rng: random.Random) -> tuple[Spec, str]:
    """Return a Spec and a borderline tag ("" if a clear case)."""
    name = rng.choice(FIRST_NAMES)
    plan = rng.choice(list(PLANS))
    border = rng.random() < BORDERLINE_SHARE
    tag = ""
    base = rng.gauss(32, 6)
    usage = _flat(rng, max(12, base))
    tenure = rng.randint(7, 11)
    s = Spec(cid, name, since_for_tenure(tenure, rng.randint(1, 15)), plan, usage)
    s.last_activity = AS_OF - timedelta(days=rng.randint(1, 10))

    if arch == "consistent" and border:
        tag = "ontime_rate"
        s.since = since_for_tenure(11, 1)
        late = rng.choice([1, 2, 3])
        periods = sorted({b["billing_period"] for b in build_rows(s)["billing_records"]})
        for p in rng.sample(periods[:-1], late):
            s.bill_overrides[p] = f"late:{rng.randint(2, 9)}"
    elif arch == "loyal":
        s.since = since_for_tenure(rng.randint(13, 48), rng.randint(1, 15))
        if border:
            if rng.random() < 0.5:
                tag = "loyalty_tenure"
                s.since = since_for_tenure(rng.choice([11, 12, 13]), 1)
            else:
                tag = "late_payment_6m"
                p = month_start(AS_OF, -rng.randint(2, 4)).strftime("%Y-%m")
                s.bill_overrides[p] = "late:4"
    elif arch == "declining":
        s.since = since_for_tenure(rng.randint(8, 40), rng.randint(1, 15))
        prior = max(12, rng.gauss(40, 8))
        if border:
            tag = "decline_ratio"
            s.since = since_for_tenure(rng.randint(7, 11), 1)
            p_int = round(prior)
            r = round(p_int * rng.uniform(0.66, 0.74))
            s.usage = [p_int] * 3 + [r] * 3
        else:
            ratio = rng.uniform(0.3, 0.62)
            s.usage = _flat(rng, prior, 3, 0.05) + _flat(rng, prior * ratio, 3, 0.05)
    elif arch == "dormant":
        s.since = since_for_tenure(rng.randint(10, 40), rng.randint(1, 15))
        days = rng.randint(55, 65) if border else rng.randint(65, 200)
        tag = "dormant_days" if border else ""
        last = AS_OF - timedelta(days=days)
        s.last_activity = last
        p = round(max(15, base))
        new_usage = []
        for k in range(6, 0, -1):
            m = month_start(AS_OF, -k)
            if m < month_start(last):
                new_usage.append(p)
            elif m == month_start(last):
                new_usage.append(max(1, round(p * last.day / 30)))
            else:
                new_usage.append(0)
        s.usage = new_usage
    elif arch in ("overdue_s1", "overdue_s3", "partial_payer", "disputed"):
        s.since = since_for_tenure(rng.randint(14, 40), rng.randint(1, 15))
        days = {"overdue_s1": (1, 10), "overdue_s3": (21, 45), "partial_payer": (5, 30),
                "disputed": (3, 20)}[arch]  # fmt: skip
        d = rng.randint(*days)
        due = AS_OF - timedelta(days=d)
        issue = due - timedelta(days=15)
        s.issue_day, s.due_days = issue.day, 15
        if issue.day > 28:  # keep issue day valid for every month
            s.issue_day, s.due_days = 28, (due - issue.replace(day=28)).days
        period = issue.strftime("%Y-%m")
        if arch == "partial_payer":
            s.bill_overrides[period] = f"partial:{s.bill_amount // 2}"
        elif arch == "disputed":
            s.bill_overrides[period] = "disputed"
        else:
            s.unpaid_from = period
    elif arch == "new_customer":
        s.since = AS_OF - timedelta(days=rng.randint(10, 80))
    elif arch == "irregular":
        s.since = since_for_tenure(rng.randint(8, 30), rng.randint(1, 15))
        while True:
            u = [rng.choice([rng.randint(1, 4), rng.randint(30, 60)]) for _ in range(6)]
            mean = statistics.mean(u)
            cv = statistics.pstdev(u) / mean
            ratio = statistics.mean(u[3:]) / statistics.mean(u[:3])
            if cv > 0.6 and ratio > 0.8 and u[5] > 4:
                break
        s.usage = u
    elif arch == "contradictory":
        latest = month_start(AS_OF, -1).strftime("%Y-%m")
        s.bill_overrides[latest] = rng.choice([
            "missing_due", f"paid_status_partial:{s.bill_amount // 2}", "overpay:10000",
            "unpaid_status_but_paid",
        ])  # fmt: skip
    elif arch == "opted_out":
        s.since = since_for_tenure(rng.randint(13, 48), rng.randint(1, 15))
        s.prefs = {"email_service_consent": 0, "email_marketing_consent": 0,
                   "email_opt_out": 1, "preferred_channel": "NONE"}  # fmt: skip
    return s, tag


def expected_labels(arch: str, s: Spec, rows: dict[str, list[dict]]) -> dict:
    """Intended truth from the archetype, refined for borderline parameters."""
    n, ok, late6 = on_time_counts(rows)
    rate = ok / n if n else None
    tenure = months_between(s.since, AS_OF)
    engagement = {
        "consistent": "CONSISTENT", "loyal": "CONSISTENT", "declining": "DECLINING_ACTIVITY",
        "dormant": "DORMANT", "new_customer": "INSUFFICIENT_DATA", "irregular": "STANDARD",
        "opted_out": "CONSISTENT",
    }.get(arch, "CONSISTENT")  # fmt: skip
    if engagement == "CONSISTENT" and (rate is None or rate < 0.80):
        engagement = "STANDARD"
    if arch == "declining" and s.usage[3] / s.usage[0] > 0.70:  # borderline ratio
        engagement = "CONSISTENT" if rate is not None and rate >= 0.80 else "STANDARD"
    if arch == "dormant" and s.last_activity and (AS_OF - s.last_activity).days < 60:
        engagement = "DECLINING_ACTIVITY"
    loyalty = (
        engagement == "CONSISTENT" and tenure >= 12 and rate is not None and rate >= 0.90
        and late6 == 0
    )  # fmt: skip
    reminder = arch in ("overdue_s1", "overdue_s3", "partial_payer")
    segments = [engagement] + (["LOYALTY_CANDIDATE"] if loyalty else [])
    segments += ["PAYMENT_REMINDER"] if reminder else []
    return {
        "expected_engagement": engagement,
        "expected_loyalty": int(loyalty),
        "expected_payment_reminder": int(reminder),
        "expected_segments": "|".join(segments),
    }


def write_split(split: str) -> None:
    n, seed, first_id = SPLITS[split]
    rng = random.Random(seed)
    archetypes = list(ARCHETYPE_WEIGHTS)
    weights = list(ARCHETYPE_WEIGHTS.values())
    tables: dict[str, list[dict]] = {}
    labels = []
    for i in range(n):
        cid = f"C{first_id + i:04d}"
        arch = rng.choices(archetypes, weights)[0]
        spec, tag = sample(arch, cid, rng)
        rows = build_rows(spec, rng)
        for t, r in rows.items():
            tables.setdefault(t, []).extend(r)
        labels.append({"customer_id": cid, "archetype": arch, "borderline": tag,
                       **expected_labels(arch, spec, rows)})  # fmt: skip
    out = ROOT / split
    out.mkdir(parents=True, exist_ok=True)
    for table, rows in tables.items():
        cols = list(models.Base.metadata.tables[table].columns.keys())
        with (out / f"{table}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    with (out / "labels.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(labels[0]))
        w.writeheader()
        w.writerows(labels)
    print(f"wrote {out} ({n} customers, seed={seed})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--split", choices=list(SPLITS))
    ap.add_argument("--demo", action="store_true", help="write data/seed/demo_customers.json")
    args = ap.parse_args()
    if not args.split and not args.demo:
        ap.error("pass --demo and/or --split dev|eval")
    if args.demo:
        write_demo()
    if args.split:
        write_split(args.split)


if __name__ == "__main__":
    main()
