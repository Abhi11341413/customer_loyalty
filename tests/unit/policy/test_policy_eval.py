"""The §14.2 policy evaluation runs in CI: every hand-written case must pass."""

import importlib.util

from config.settings import PROJECT_ROOT

SCRIPT = PROJECT_ROOT / "evaluation" / "policy" / "run.py"


def _run():
    spec = importlib.util.spec_from_file_location("policy_eval", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.evaluate()


def test_policy_evaluation_meets_every_target():
    res = _run()
    assert res["failures"] == []
    for name, m in res["metrics"].items():
        assert m["rate"] == 1.0, f"{name}: {m}"


def test_case_tables_are_large_enough():
    """§14.2 asks for at least 25 billing and 25 offer cases."""
    m = _run()["metrics"]
    assert m["billing_rule_correctness"]["total"] >= 25
    assert m["offer_eligibility_accuracy"]["total"] >= 25
