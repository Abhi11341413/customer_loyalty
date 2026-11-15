"""GuardrailRunner + severity aggregation (§9.3).

Owner: M3.

Precedence: BLOCK > ESCALATE > WARN > PASS. The runner never rewrites text (it may
only report). It fails closed: a mandatory check that crashes produces a BLOCK.
"""

from __future__ import annotations

import logging

from app.generation.content import DisclaimerStore, TemplateStore
from app.guardrails.base import GuardrailCheck, VerifiedFacts, load_resources
from app.guardrails.registry import default_checks
from app.schemas.enums import Severity
from app.schemas.generation import RenderedDraft
from app.schemas.validation import (
    SEVERITY_RANK,
    Finding,
    ValidationContext,
    ValidationReport,
)

log = logging.getLogger(__name__)


def aggregate(findings: list[Finding]) -> Severity:
    worst = Severity.PASS
    for f in findings:
        if SEVERITY_RANK[f.severity] > SEVERITY_RANK[worst]:
            worst = f.severity
    return worst


class GuardrailRunner:
    def __init__(
        self, checks: list[GuardrailCheck], disclaimers: DisclaimerStore, version: str
    ) -> None:
        ids = [c.check_id for c in checks]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate check ids: {ids}")
        self._checks = list(checks)
        self._disclaimers = disclaimers
        self.version = version

    @classmethod
    def default(cls, templates: TemplateStore | None = None) -> GuardrailRunner:
        res = load_resources()
        return cls(default_checks(res, templates or TemplateStore()), res.disclaimers, res.version)

    @property
    def check_ids(self) -> list[str]:
        return [c.check_id for c in self._checks]

    def validate(self, draft: RenderedDraft, ctx: ValidationContext) -> ValidationReport:
        facts = VerifiedFacts(ctx, self._disclaimers)
        findings: list[Finding] = []
        run: list[str] = []
        skipped: list[str] = []
        for check in self._checks:
            try:
                result = check.run(draft, ctx, facts)
            except Exception:
                log.exception("guardrail check %s crashed", check.check_id)
                result = [
                    Finding(
                        check_id=check.check_id,
                        severity=Severity.BLOCK if check.mandatory else Severity.WARN,
                        mandatory=check.mandatory,
                        message="Check failed to run (treated as failure)",
                    )
                ]
            if result is None:
                skipped.append(check.check_id)
                continue
            run.append(check.check_id)
            if result:
                findings.extend(result)
            else:
                findings.append(
                    Finding(
                        check_id=check.check_id,
                        severity=Severity.PASS,
                        mandatory=check.mandatory,
                        message="passed",
                    )
                )
        return ValidationReport(
            overall=aggregate(findings),
            findings=findings,
            checks_run=run,
            checks_skipped=skipped,
            content_hash=draft.content_hash,
            guardrail_version=self.version,
        )
