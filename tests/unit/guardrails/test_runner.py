"""GuardrailRunner: severity aggregation, fail-closed behaviour, skipped checks, config."""

import pytest

from app.generation.content import DisclaimerStore
from app.guardrails.base import load_resources
from app.guardrails.runner import GuardrailRunner, aggregate
from app.schemas.enums import Objective, Severity
from app.schemas.validation import Finding
from tests.support import m3

OBJ = Objective.APPRECIATION


def _f(sev: Severity) -> Finding:
    return Finding(check_id="X", severity=sev, mandatory=sev is Severity.BLOCK, message="m")


@pytest.mark.parametrize(
    "severities,expected",
    [
        ([], Severity.PASS),
        ([Severity.PASS, Severity.PASS], Severity.PASS),
        ([Severity.PASS, Severity.WARN], Severity.WARN),
        ([Severity.WARN, Severity.ESCALATE], Severity.ESCALATE),
        ([Severity.ESCALATE, Severity.BLOCK, Severity.WARN], Severity.BLOCK),
    ],
)
def test_aggregation_precedence(severities, expected):
    assert aggregate([_f(s) for s in severities]) is expected


class _Check:
    def __init__(self, check_id, mandatory, result=None, crash=False):
        self.check_id, self.mandatory, self._result, self._crash = (
            check_id,
            mandatory,
            result,
            crash,
        )

    def run(self, draft, ctx, facts):
        if self._crash:
            raise RuntimeError("bug")
        return self._result


def _runner(*checks):
    return GuardrailRunner(list(checks), DisclaimerStore(), "test")


def test_crashing_mandatory_check_fails_closed():
    r = _runner(_Check("A", True, crash=True)).validate(m3.rendered(OBJ), m3.ctx(OBJ))
    assert r.overall is Severity.BLOCK and not r.approvable


def test_crashing_advisory_check_only_warns():
    r = _runner(_Check("A", False, crash=True)).validate(m3.rendered(OBJ), m3.ctx(OBJ))
    assert r.overall is Severity.WARN


def test_none_result_is_skipped_not_passed():
    r = _runner(_Check("A", True, result=None), _Check("B", True, result=[])).validate(
        m3.rendered(OBJ), m3.ctx(OBJ)
    )
    assert r.checks_skipped == ["A"] and r.checks_run == ["B"]
    assert [(f.check_id, f.severity) for f in r.findings] == [("B", Severity.PASS)]


def test_duplicate_check_ids_rejected():
    with pytest.raises(ValueError):
        _runner(_Check("A", True, []), _Check("A", False, []))


def test_report_binds_to_content_hash_and_version():
    d = m3.rendered(OBJ)
    r = m3.runner().validate(d, m3.ctx(OBJ))
    assert r.content_hash == d.content_hash
    assert r.guardrail_version == m3.runner().version


def test_blocked_language_config_validates():
    res = load_resources()
    assert ("threats", "legal action") in res.config.blocked_terms
    assert "BILLING_REMINDER_COURTEOUS" in res.config.pressure_terms_warn_in
