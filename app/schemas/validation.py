"""Finding, ValidationReport, ValidationContext.

Owner: SHARED (produced by M3). Drafted by M4 for CP0 from blueprint sections 9.2-9.3;
needs approval.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import Severity
from app.schemas.generation import LLMInput
from app.schemas.policy import StrategyDecision


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: str
    severity: Severity
    mandatory: bool
    message: str  # human-readable, no PII
    span: str | None = Field(default=None, max_length=80)


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    overall: Severity
    findings: list[Finding] = []
    validation_run: int = 1


class ValidationContext(BaseModel):
    """What the guardrails need to judge a draft. Stored with the draft so edits can be
    re-validated against exactly the same verified facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    llm_input: LLMInput
    strategy: StrategyDecision


def aggregate_severity(findings: list[Finding]) -> Severity:
    """Overall verdict: BLOCK > ESCALATE > WARN > PASS."""
    worst = Severity.PASS
    for finding in findings:
        if finding.severity.rank > worst.rank:
            worst = finding.severity
    return worst
