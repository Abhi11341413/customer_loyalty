"""M2's contract fixtures must validate against the shared schemas and match real output.

If this fails after an intended change, regenerate:
    python evaluation/policy/make_contract_fixtures.py
"""

import importlib.util
import json

import pytest

from app.schemas.generation import LLMInput
from app.schemas.policy import BillingDecision, ContactDecision, OfferDecision, StrategyDecision
from config.settings import PROJECT_ROOT

CONTRACTS = PROJECT_ROOT / "tests" / "fixtures" / "contracts"
SCRIPT = PROJECT_ROOT / "evaluation" / "policy" / "make_contract_fixtures.py"

MODELS = {
    "billing_decision": BillingDecision,
    "offer_decision": OfferDecision,
    "strategy_decision": StrategyDecision,
    "llm_input": LLMInput,
}


def _load_script():
    spec = importlib.util.spec_from_file_location("make_contract_fixtures", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def generated(demo_engine):
    from sqlalchemy.orm import Session

    with Session(demo_engine) as s:
        return _load_script().build(s)


def test_every_fixture_is_committed_and_up_to_date(generated):
    for name, text in generated.items():
        path = CONTRACTS / name
        assert path.exists(), f"missing {name} — run evaluation/policy/make_contract_fixtures.py"
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk == json.loads(text), f"{name} is stale — regenerate the fixtures"


def test_fixtures_validate_against_schemas(generated):
    for name in generated:
        data = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
        kind = name.rsplit("_", 1)[0]
        if kind == "contact_decisions":
            for decision in data.values():
                ContactDecision.model_validate(decision)
        else:
            MODELS[kind].model_validate(data)


def test_llm_input_fixtures_contain_no_identifiers(generated):
    for name in (n for n in generated if n.startswith("llm_input_")):
        text = (CONTRACTS / name).read_text(encoding="utf-8")
        assert "@" not in text and "example.test" not in text
        cid = name.removeprefix("llm_input_").removesuffix(".json")
        assert cid not in text
