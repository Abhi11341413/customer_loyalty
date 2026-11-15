"""Classification evaluation: per-class precision/recall/F1, macro-F1, confusion matrices,
strategy-level confusion and severe-error count.

Owner: M1.

Usage (from the project root):
    python evaluation/classification/run.py --split demo
    python evaluation/classification/run.py --split dev
    python evaluation/classification/run.py --split eval
    python evaluation/classification/run.py --labelled        # labelled_scenarios.jsonl (M2/M3)

Writes evaluation/reports/classification_<split>.md.

Multi-label handling: engagement axis = multiclass; LOYALTY_CANDIDATE and PAYMENT_REMINDER =
separate binary tasks; plus exact-set match rate.

NOTE on synthetic labels: dev/eval labels come from the generator's archetypes (intended truth).
They test that rules match the business definitions, not that the definitions are right. The
independent check is the hand-labelled set, labelled by M2/M3 (not by M1, the rule author).
"""

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sqlalchemy.orm import Session

from app.data.db import make_engine
from app.data.models import Base
from app.data.seed import SYNTHETIC_DIR, build_dataset, load_tables
from app.data.seed import read_catalogue as _catalogue
from app.segmentation.service import ClassificationService

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "evaluation" / "reports"
LABELLED = ROOT / "evaluation" / "datasets" / "labelled_scenarios.jsonl"
DEMO = ROOT / "data" / "seed" / "demo_customers.json"
AS_OF = date(2026, 11, 15)

ENGAGEMENT = ["INSUFFICIENT_DATA", "DORMANT", "DECLINING_ACTIVITY", "CONSISTENT", "STANDARD"]

# Coarse objective a segment set leads to (mirrors the strategy precedence; M2 owns the real map).
STRATEGIES = ["ESCALATE", "BILLING_REMINDER", "LOYALTY_REWARD", "WINBACK", "REENGAGEMENT",
              "APPRECIATION", "NO_CONTACT"]  # fmt: skip
SEVERE = {  # (true, predicted) pairs that change the tone class -> customer harm
    *{(t, "BILLING_REMINDER") for t in ("LOYALTY_REWARD", "APPRECIATION", "REENGAGEMENT",
                                         "WINBACK", "NO_CONTACT")},
    *{("BILLING_REMINDER", p) for p in ("LOYALTY_REWARD", "APPRECIATION", "REENGAGEMENT",
                                         "WINBACK", "NO_CONTACT")},
    *{(t, "LOYALTY_REWARD") for t in ("BILLING_REMINDER", "REENGAGEMENT", "WINBACK",
                                       "NO_CONTACT", "ESCALATE")},
}  # fmt: skip


def strategy(segments: set[str]) -> str:
    if "INSUFFICIENT_DATA" in segments:
        return "ESCALATE"
    for seg, strat in (
        ("PAYMENT_REMINDER", "BILLING_REMINDER"),
        ("LOYALTY_CANDIDATE", "LOYALTY_REWARD"),
        ("DORMANT", "WINBACK"),
        ("DECLINING_ACTIVITY", "REENGAGEMENT"),
        ("CONSISTENT", "APPRECIATION"),
    ):
        if seg in segments:
            return strat
    return "NO_CONTACT"


def load_cases(split: str | None, labelled: bool) -> tuple[dict, list[dict]]:
    """Return (tables to seed, cases [{customer_id, expected_segments: set}])."""
    if labelled:
        if not LABELLED.exists() or not LABELLED.read_text(encoding="utf-8").strip():
            sys.exit(f"{LABELLED} is empty — M2/M3 label the scenarios (see the blueprint §14.7)")
        tables: dict = {k: list(v) for k, v in _catalogue().items()}
        cases = []
        for line in LABELLED.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            for key, rows in item["input"].items():
                table = {
                    "customer": "customers",
                    "contact_preferences": "customer_contact_preferences",
                }.get(key, key)
                tables.setdefault(table, []).extend(rows if isinstance(rows, list) else [rows])
            cid = item["input"]["customer"]["customer_id"]
            cases.append({"customer_id": cid, "expected": set(item["expected"]["segments"])})
        return tables, cases
    tables = build_dataset(split)
    if split == "demo":
        data = json.loads(DEMO.read_text(encoding="utf-8"))
        cases = [
            {
                "customer_id": c["customer"]["customer_id"],
                "expected": set(c["expected"]["segments"]),
            }
            for c in data["customers"]
        ]
    else:
        with (SYNTHETIC_DIR / split / "labels.csv").open(encoding="utf-8") as f:
            cases = [
                {
                    "customer_id": r["customer_id"],
                    "archetype": r["archetype"],
                    "borderline": r["borderline"],
                    "expected": set(r["expected_segments"].split("|")),
                }
                for r in csv.DictReader(f)
            ]
    return tables, cases


def evaluate(tables: dict, cases: list[dict]) -> dict:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        load_tables(s, tables)
        svc = ClassificationService.from_session(s)
        for c in cases:
            res = svc.classify(c["customer_id"], AS_OF, persist=False).result
            c["predicted"] = {seg.value for seg in res.segments}
            c["confidence_band"] = res.confidence_band.value

    def eng(segs: set[str]) -> str:
        return next(s for s in ENGAGEMENT if s in segs)

    y_true = [eng(c["expected"]) for c in cases]
    y_pred = [eng(c["predicted"]) for c in cases]
    s_true = [strategy(c["expected"]) for c in cases]
    s_pred = [strategy(c["predicted"]) for c in cases]
    binary = {}
    for flag in ("LOYALTY_CANDIDATE", "PAYMENT_REMINDER"):
        t = [int(flag in c["expected"]) for c in cases]
        p = [int(flag in c["predicted"]) for c in cases]
        binary[flag] = classification_report(
            t, p, labels=[0, 1], target_names=["no", "yes"], zero_division=0, digits=3
        )
    severe = [c for c, t, p in zip(cases, s_true, s_pred, strict=True) if (t, p) in SEVERE]
    return {
        "n": len(cases),
        "exact": sum(c["expected"] == c["predicted"] for c in cases) / len(cases),
        # macro over classes that occur, so absent classes don't count as F1 = 0
        "macro_f1": f1_score(y_true, y_pred, average="macro", zero_division=0,
                             labels=[c for c in ENGAGEMENT if c in y_true or c in y_pred]),
        "report": classification_report(y_true, y_pred, labels=ENGAGEMENT, zero_division=0,
                                        digits=3),
        "cm": confusion_matrix(y_true, y_pred, labels=ENGAGEMENT),
        "scm": confusion_matrix(s_true, s_pred, labels=STRATEGIES),
        "binary": binary,
        "severe": severe,
        "errors": [c for c in cases if c["expected"] != c["predicted"]],
    }  # fmt: skip


def _matrix(labels: list[str], cm) -> str:
    head = "| true \\ pred | " + " | ".join(labels) + " |\n"
    head += "|---" * (len(labels) + 1) + "|\n"
    return head + "".join(
        f"| **{lab}** | " + " | ".join(str(v) for v in row) + " |\n"
        for lab, row in zip(labels, cm, strict=True)
    )


def render(name: str, r: dict) -> str:
    lines = [
        f"# Classification evaluation — {name}\n",
        f"As of {AS_OF}. Cases: **{r['n']}**. Exact segment-set match: "
        f"**{r['exact']:.1%}**. Engagement macro-F1: **{r['macro_f1']:.3f}**. "
        f"Severe strategy errors: **{len(r['severe'])}**.\n",
        "## Engagement axis (multiclass)\n", "```\n" + r["report"] + "```\n",
        _matrix(ENGAGEMENT, r["cm"]),
        "\n## Qualifier / flag (binary)\n",
    ]  # fmt: skip
    for flag, rep in r["binary"].items():
        lines += [f"**{flag}**\n", "```\n" + rep + "```\n"]
    lines += ["## Strategy-level confusion\n", _matrix(STRATEGIES, r["scm"])]
    lines.append("\n## Mismatches\n")
    if not r["errors"]:
        lines.append("None.\n")
    for c in r["errors"]:
        extra = f" ({c.get('archetype')}{', ' + c['borderline'] if c.get('borderline') else ''})"
        lines.append(f"- {c['customer_id']}{extra if c.get('archetype') else ''}: expected "
                     f"{sorted(c['expected'])}, predicted {sorted(c['predicted'])} "
                     f"[{c['confidence_band']}]\n")  # fmt: skip
    lines.append(
        "\n> Limitations: synthetic labels reflect the intended business definitions "
        "(ASSUMPTIONS in segments.yaml); they do not validate the definitions themselves.\n"
    )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["demo", "dev", "eval"], default="demo")
    ap.add_argument("--labelled", action="store_true")
    args = ap.parse_args()
    name = "labelled" if args.labelled else args.split
    tables, cases = load_cases(None if args.labelled else args.split, args.labelled)
    result = evaluate(tables, cases)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"classification_{name}.md"
    out.write_text(render(name, result), encoding="utf-8")
    print(
        f"{name}: n={result['n']} exact={result['exact']:.1%} "
        f"macro_f1={result['macro_f1']:.3f} severe={len(result['severe'])} -> {out}"
    )


if __name__ == "__main__":
    main()
