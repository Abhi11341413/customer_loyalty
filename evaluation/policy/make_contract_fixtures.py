"""Regenerate M2's contract fixtures in tests/fixtures/contracts/.

Owner: M2. M3 (generation) and M4 (orchestrator/UI) build against these JSON examples
instead of waiting for the real engine. tests/unit/policy/test_contract_fixtures.py fails
if they drift from the engine's real output — re-run this script after an intended change:

    python evaluation/policy/make_contract_fixtures.py
"""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from app.data.db import make_engine  # noqa: E402
from app.data.seed import seed  # noqa: E402
from app.policy.service import PolicyService  # noqa: E402
from app.schemas.enums import NON_DRAFT_OBJECTIVES  # noqa: E402
from app.segmentation.service import ClassificationService  # noqa: E402

CONTRACTS = ROOT / "tests" / "fixtures" / "contracts"
AS_OF = date(2026, 11, 15)

#: one customer per kind of decision the other members must handle
CUSTOMERS = {
    "C0002": "loyalty reward with a verified offer",
    "C0005": "courteous billing reminder (stage 1)",
    "C0007": "refusal: opted out (NO_CONTACT_BY_POLICY)",
    "C0009": "loyal + overdue: reminder only, reward deferred",
    "C0010": "escalation: disputed bill",
}


def build(session: Session) -> dict[str, str]:
    """Return {file name: JSON text} for every fixture."""
    classify = ClassificationService.from_session(session)
    policy = PolicyService.from_session(session)
    files: dict[str, str] = {}
    for cid in CUSTOMERS:
        out = classify.classify(cid, AS_OF, persist=False)
        a = policy.analyze(out.profile, out.features, out.result)
        docs = {
            f"billing_decision_{cid}.json": a.billing.model_dump(mode="json"),
            f"offer_decision_{cid}.json": a.offers.model_dump(mode="json"),
            f"contact_decisions_{cid}.json": {
                str(k): v.model_dump(mode="json") for k, v in a.contact.items()
            },
            f"strategy_decision_{cid}.json": a.strategy.model_dump(mode="json"),
        }
        if a.strategy.objective not in NON_DRAFT_OBJECTIVES:
            inp = policy.llm_input.build(out.profile, out.result, a.billing, a.strategy)
            docs[f"llm_input_{cid}.json"] = inp.model_dump(mode="json")
        for name, doc in docs.items():
            files[name] = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    return files


def main() -> None:
    engine = make_engine("sqlite://")
    seed("demo", engine)
    with Session(engine) as session:
        files = build(session)
    CONTRACTS.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (CONTRACTS / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {len(files)} fixtures to {CONTRACTS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
