"""Policy engine evaluation (CLAUDE.md §14.2).

Owner: M2.

Usage (from the project root):
    python evaluation/policy/run.py

Runs the hand-written case tables in evaluation/policy/cases/ through the real engine, plus
the strategy for the ten demo customers (§16), and writes
    evaluation/reports/policy_evaluation.md   (human-readable, goes into the report)
    evaluation/reports/policy_metrics.json    (machine-readable)

Exit code 1 if any metric with a 100% target misses it — usable as a CI gate.

Limitation: this measures correctness against OUR ASSUMED policy (the YAML files), not
against any real company's policy.
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.policy.billing import decide_billing  # noqa: E402
from app.policy.config import (  # noqa: E402
    load_billing_config,
    load_contact_config,
)
from app.policy.contact import check_contact  # noqa: E402
from app.policy.offers import decide_offers  # noqa: E402
from app.schemas.campaign import Campaign, CampaignOffer, OfferRedemption  # noqa: E402
from app.schemas.customer import (  # noqa: E402
    BillingRecord,
    CommunicationRecord,
    ContactPreferences,
    Payment,
)
from app.schemas.enums import AccountStatus, BillState, MessageCategory, Segment  # noqa: E402
from app.schemas.policy import OfferCustomerContext  # noqa: E402

CASES = ROOT / "evaluation" / "policy" / "cases"
LABELLED = ROOT / "evaluation" / "datasets" / "labelled_scenarios.jsonl"
REPORTS = ROOT / "evaluation" / "reports"
AS_OF = date(2026, 11, 15)

#: §16 demo table: customer -> expected objective
DEMO_EXPECTED = {
    "C0001": "APPRECIATION",
    "C0002": "LOYALTY_REWARD",
    "C0003": "REENGAGEMENT",
    "C0004": "WINBACK",
    "C0005": "BILLING_REMINDER_COURTEOUS",
    "C0006": "BILLING_REMINDER_FIRM",
    "C0007": "NO_CONTACT_BY_POLICY",
    "C0008": "REENGAGEMENT",
    "C0009": "BILLING_REMINDER_FOLLOWUP",
    "C0010": "ESCALATE",
}


def _ago(n: int) -> date:
    return AS_OF - timedelta(days=n)


def _ts(n: int) -> datetime:
    return datetime.combine(_ago(n), time(9, 0), tzinfo=UTC)


_seq = iter(range(1, 1_000_000))


def _comm(n_ago: int, category: str, objective: str, **kw) -> CommunicationRecord:
    return CommunicationRecord(
        comm_id=f"CM-{next(_seq)}", sent_at=_ts(n_ago), channel="EMAIL", category=category,
        objective=objective, source="HISTORICAL_SEED", **kw,
    )  # fmt: skip


def load(name: str) -> list[dict]:
    return yaml.safe_load((CASES / name).read_text(encoding="utf-8")) or []


@dataclass
class Result:
    case_id: str
    desc: str
    ok: bool
    tags: list[str] = field(default_factory=list)
    detail: str = ""
    passed_tag_check: bool = True  # for tagged metrics (blocked / escalated / rejected)


# --------------------------------------------------------------------------- billing


def run_billing_case(case: dict) -> Result:
    cfg = load_billing_config()
    bills = []
    for b in case.get("bills", []):
        due = None if b.get("due_ago") is None else _ago(b["due_ago"])
        issue_ago = b.get("issue_ago", (b.get("due_ago") or 0) + 14)
        bills.append(BillingRecord(
            bill_id=f"B-{b['period']}", billing_period=b["period"], issue_date=_ago(issue_ago),
            due_date=due, amount_due_minor=b.get("amount", 59900),
            status=b.get("status", "UNPAID"), dispute_status=b.get("dispute", "NONE"),
        ))  # fmt: skip
    payments = [
        Payment(payment_id=f"P-{i}", bill_id=f"B-{p['period']}", paid_date=_ago(p["ago"]),
                amount_paid_minor=p["amount"])
        for i, p in enumerate(case.get("payments", []))
    ]  # fmt: skip
    history = [
        _comm(r["ago"], "SERVICE", r.get("objective", "BILLING_REMINDER"),
              reminder_stage=r.get("stage"), related_bill_id=f"B-{r['period']}")
        for r in case.get("reminders", [])
    ]  # fmt: skip
    d = decide_billing(bills, payments, history, cfg, AS_OF)

    exp = case["expected"]
    problems = []
    if d.state.value != exp["state"]:
        problems.append(f"state {d.state.value} != {exp['state']}")
    if d.reminder_allowed != exp["reminder_allowed"]:
        problems.append(f"reminder_allowed {d.reminder_allowed} != {exp['reminder_allowed']}")
    if d.escalate != exp.get("escalate", False):
        problems.append(f"escalate {d.escalate} != {exp.get('escalate', False)}")
    if "stage" in exp and d.stage != exp["stage"]:
        problems.append(f"stage {d.stage} != {exp['stage']}")
    if "reason" in exp and exp["reason"] not in d.reason_codes:
        problems.append(f"reason {exp['reason']} not in {d.reason_codes}")
    if "amount_due" in exp and d.verified_facts.get("amount_due") != exp["amount_due"]:
        problems.append(f"amount_due {d.verified_facts.get('amount_due')} != {exp['amount_due']}")
    if "bill_period" in exp and d.bill_id != f"B-{exp['bill_period']}":
        problems.append(f"bill {d.bill_id} != B-{exp['bill_period']}")

    tags = case.get("tags", [])
    tag_ok = True
    if "duplicate" in tags:
        tag_ok = not d.reminder_allowed
    if "conflict" in tags:
        tag_ok = d.escalate and not d.reminder_allowed
    return Result(case["id"], case["desc"], not problems, tags, "; ".join(problems), tag_ok)


# --------------------------------------------------------------------------- offers

_BASE_OFFER = dict(
    offer_id="OFF-LOY-200", campaign_id="CMP-LOY-Q4", offer_type="LOYALTY_REWARD",
    title="Loyalty credit", value_type="FLAT_CREDIT_MINOR", value=20000,
    terms_summary="One-time ₹200 bill credit, applied on next bill.",
    valid_from="2026-11-01", valid_to="2026-12-31", channel="EMAIL",
    eligible_segments=["LOYALTY_CANDIDATE"], min_tenure_months=12, requires_no_overdue=True,
    max_per_customer=1, total_cap=500, total_redeemed=37,
)  # fmt: skip
_BASE_CAMPAIGN = dict(
    campaign_id="CMP-LOY-Q4", name="Loyalty Q4 2026", status="ACTIVE",
    start_date="2026-11-01", end_date="2026-12-31",
)  # fmt: skip
_BASE_CUSTOMER = dict(
    customer_id="C0002", segments=["CONSISTENT", "LOYALTY_CANDIDATE"], tenure_months=31,
    active_plan_ids=["PL-POST-499"], account_status="ACTIVE", bill_state="PAID",
)  # fmt: skip


def run_offer_case(case: dict) -> Result:
    offer = CampaignOffer(**{**_BASE_OFFER, **case.get("offer", {})})
    campaigns = []
    if case.get("campaign", {}) is not None:
        campaigns = [Campaign(**{**_BASE_CAMPAIGN, **case.get("campaign", {})})]
    c = {**_BASE_CUSTOMER, **case.get("customer", {})}
    customer = OfferCustomerContext(
        customer_id=c["customer_id"],
        segments=frozenset(Segment(s) for s in c["segments"]),
        tenure_months=c["tenure_months"],
        active_plan_ids=frozenset(c["active_plan_ids"]),
        account_status=AccountStatus(c["account_status"]),
        bill_state=BillState(c["bill_state"]),
    )
    redemptions = [
        OfferRedemption(redemption_id=f"R-{i}", offer_id=offer.offer_id,
                        customer_id=r["customer_id"], redeemed_at=_ts(r["ago"]))
        for i, r in enumerate(case.get("redemptions", []))
    ]  # fmt: skip
    history = [
        _comm(h["ago"], "MARKETING", "LOYALTY_REWARD", offer_id=h["offer_id"])
        for h in case.get("history", [])
    ]
    decision = decide_offers(
        customer, [offer], campaigns, redemptions=redemptions, history=history, as_of=AS_OF,
        candidate_offer_ids=case.get("candidate_offer_ids"),
        duplicate_window_days=load_contact_config().duplicate_window_days.same_offer,
    )  # fmt: skip
    evaluations = decision.eligible + decision.rejected
    assert len(evaluations) == 1, "each offer case evaluates exactly one offer"
    ev = evaluations[0]
    want = set(case["expected"]["failed"])
    ok = ev.eligible == (not want) and set(ev.failed_checks) == want
    detail = "" if ok else f"got {sorted(ev.failed_checks)} want {sorted(want)}"
    tags = case.get("tags", [])
    return Result(
        case["id"], case["desc"], ok, tags, detail, not ev.eligible if "invalid" in tags else True
    )


# --------------------------------------------------------------------------- contact

_BASE_PREFS = dict(
    email_service_consent=True, email_marketing_consent=True, email_opt_out=False,
    preferred_channel="EMAIL", do_not_contact_until=None, consent_updated_at=_ts(60),
)  # fmt: skip


def run_contact_case(case: dict) -> Result:
    prefs = (
        None
        if case.get("prefs", {}) is None
        else ContactPreferences(**{**_BASE_PREFS, **case.get("prefs", {})})
    )
    history = [_comm(h["ago"], h["category"], h["objective"]) for h in case.get("history", [])]
    d = check_contact(
        prefs, AccountStatus(case.get("account_status", "ACTIVE")), history,
        MessageCategory(case["category"]), case.get("objective"), load_contact_config(), AS_OF,
    )  # fmt: skip
    want = case["expected"]["reasons"]
    ok = d.reasons == want and d.allowed == (not want)
    return Result(case["id"], case["desc"], ok, [], "" if ok else f"got {d.reasons} want {want}")


# --------------------------------------------------------------------------- demo strategy


def run_demo_strategy() -> list[Result]:
    from sqlalchemy.orm import Session

    from app.data.db import make_engine
    from app.data.seed import seed
    from app.policy.service import PolicyService
    from app.segmentation.service import ClassificationService

    engine = make_engine("sqlite://")
    seed("demo", engine)
    out: list[Result] = []
    with Session(engine) as s:
        classify, policy = ClassificationService.from_session(s), PolicyService.from_session(s)
        for cid, want in DEMO_EXPECTED.items():
            o = classify.classify(cid, AS_OF, persist=False)
            got = policy.analyze(o.profile, o.features, o.result).strategy.objective.value
            out.append(
                Result(
                    cid,
                    f"demo {cid}",
                    got == want,
                    [],
                    "" if got == want else f"got {got} want {want}",
                )
            )
    return out


def run_labelled() -> list[Result]:
    """Objective, offer and bill state on the hand-labelled scenarios (M2 + M3 halves)."""
    from sqlalchemy.orm import Session

    from app.data.db import make_engine
    from app.data.models import Base
    from app.data.seed import load_tables, read_catalogue
    from app.policy.service import PolicyService
    from app.segmentation.service import ClassificationService

    if not LABELLED.exists():
        return []
    items = [json.loads(x) for x in LABELLED.read_text(encoding="utf-8").splitlines() if x.strip()]
    items = [i for i in items if i.get("expected", {}).get("objective")]
    tables: dict = {k: list(v) for k, v in read_catalogue().items()}
    for it in items:
        for key, rows in it["input"].items():
            name = {"customer": "customers", "contact_preferences": "customer_contact_preferences"}
            tables.setdefault(name.get(key, key), []).extend(
                rows if isinstance(rows, list) else [rows]
            )
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    out: list[Result] = []
    with Session(engine) as s:
        load_tables(s, tables)
        s.commit()
        classify, policy = ClassificationService.from_session(s), PolicyService.from_session(s)
        for it in items:
            o = classify.classify(it["id"], AS_OF, persist=False)
            a = policy.analyze(o.profile, o.features, o.result)
            got = {
                "objective": a.strategy.objective.value,
                "offer_id": a.strategy.allowed_offer.offer_id if a.strategy.allowed_offer else None,
                "billing_state": a.billing.state.value,
            }
            diff = {
                k: f"{got[k]} != {it['expected'][k]}"
                for k in got
                if got[k] != it["expected"].get(k)
            }
            out.append(
                Result(
                    it["id"],
                    it.get("description", ""),
                    not diff,
                    [it.get("category", "")],
                    "; ".join(diff.values()),
                )
            )
    return out


# --------------------------------------------------------------------------- report


def _rate(hits: int, total: int) -> float:
    return round(hits / total, 4) if total else 1.0


def evaluate() -> dict:
    billing = [run_billing_case(c) for c in load("billing_cases.yaml")]
    offers = [run_offer_case(c) for c in load("offer_cases.yaml")]
    contact = [run_contact_case(c) for c in load("contact_cases.yaml")]
    demo = run_demo_strategy()
    labelled = run_labelled()

    def tagged(results, tag):
        return [r for r in results if tag in r.tags]

    dup, conflict, invalid = (
        tagged(billing, "duplicate"),
        tagged(billing, "conflict"),
        tagged(offers, "invalid"),
    )
    metrics = {
        "billing_rule_correctness": (sum(r.ok for r in billing), len(billing), None),
        "offer_eligibility_accuracy": (sum(r.ok for r in offers), len(offers), None),
        "invalid_offer_rejection_rate": (
            sum(r.passed_tag_check for r in invalid),
            len(invalid),
            1.0,
        ),
        "duplicate_reminder_prevention": (sum(r.passed_tag_check for r in dup), len(dup), 1.0),
        "contradictory_data_handling": (
            sum(r.passed_tag_check for r in conflict),
            len(conflict),
            1.0,
        ),
        "contact_gate_accuracy": (sum(r.ok for r in contact), len(contact), None),
        "demo_strategy_match": (sum(r.ok for r in demo), len(demo), 1.0),
        "labelled_scenarios_policy_match": (sum(r.ok for r in labelled), len(labelled), None),
    }
    return {
        "as_of": AS_OF.isoformat(),
        "metrics": {
            k: {"hits": h, "total": t, "rate": _rate(h, t), "target": tgt}
            for k, (h, t, tgt) in metrics.items()
        },
        "failures": [
            {"case": r.case_id, "desc": r.desc, "detail": r.detail}
            for r in billing + offers + contact + demo + labelled
            if not r.ok
        ],
    }


def to_markdown(res: dict) -> str:
    lines = [
        "# Policy engine evaluation",
        "",
        f"Generated by `python evaluation/policy/run.py` (as of {res['as_of']}). Owner: M2.",
        "",
        "Cases are hand-written from CLAUDE.md §6-7 and the policy YAMLs "
        "(`evaluation/policy/cases/`), not copied from engine output.",
        "",
        "| Metric | Result | Target |",
        "|---|---|---|",
    ]
    for name, m in res["metrics"].items():
        target = "100%" if m["target"] == 1.0 else "—"
        lines.append(
            f"| {name.replace('_', ' ')} | {m['hits']}/{m['total']} ({m['rate']:.0%}) | {target} |"
        )
    lines += ["", "## Failures", ""]
    lines += [f"- **{f['case']}** {f['desc']}: {f['detail']}" for f in res["failures"]] or ["None."]
    lines += [
        "",
        "## Limitations",
        "",
        "- Correctness is measured against our *assumed* policy (illustrative thresholds in "
        "`config/policies/*.yaml`), not a real company's policy.",
        "- Case tables were written by the policy author (M2); an independent reviewer should "
        "spot-check them.",
        "- The duplicate-objective rule of the contact gate needs the chosen objective; in the "
        "orchestrated pipeline it is covered by the 14-day marketing gap and the 7-day per-bill "
        "reminder gap instead.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # ₹ on Windows consoles
    res = evaluate()
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "policy_metrics.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    md = to_markdown(res)
    (REPORTS / "policy_evaluation.md").write_text(md, encoding="utf-8")
    print(md)
    missed = [k for k, m in res["metrics"].items() if m["target"] and m["rate"] < m["target"]]
    if missed:
        print(f"TARGET MISSED: {missed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
