"""ValidationContext, Finding, ValidationReport (FR-07, §9).

Owner: SHARED (produced by M3) — all owners must approve changes (CLAUDE.md §12.1).

``ValidationContext`` is built by the orchestrator (M4). It carries the verified
``LLMInput`` (the only facts a draft may contain) plus optional state the guardrails
cannot look up themselves (the guardrail layer has no DB access, §3.4). Optional
fields left as ``None`` mean "not evaluated here"; the check is reported in
``checks_skipped`` instead of passing silently, and DeliveryGate re-checks them.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import ConfidenceBand, Severity
from app.schemas.generation import LLMInput

SEVERITY_RANK: dict[Severity, int] = {
    Severity.PASS: 0,
    Severity.WARN: 1,
    Severity.ESCALATE: 2,
    Severity.BLOCK: 3,
}


class ValidationContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    llm_input: LLMInput
    #: From ContactPolicyGate re-run at validation time (CONSENT_STILL_VALID).
    contact_allowed: bool | None = None
    contact_reasons: list[str] = Field(default_factory=list)
    #: True if another draft for the same customer+objective is pending/delivered
    #: inside the duplicate window (DUPLICATE_OUTREACH).
    duplicate_outreach: bool | None = None
    #: From ClassificationResult (LOW_CONFIDENCE_SEGMENT).
    confidence_band: ConfidenceBand | None = None
    shadow_agrees: bool | None = None


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    check_id: str
    severity: Severity
    mandatory: bool
    message: str
    field: Literal["subject", "body"] | None = None
    span: str | None = None  # offending text, for highlighting in the UI
    start: int | None = None  # char offsets into `field`
    end: int | None = None


class ValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    overall: Severity
    findings: list[Finding]  # failures + one PASS finding per passing check
    checks_run: list[str]
    checks_skipped: list[str] = Field(default_factory=list)
    content_hash: str  # the text this report applies to
    guardrail_version: str  # hash of guardrail config files

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is not Severity.PASS]

    @property
    def approvable(self) -> bool:
        return self.overall in (Severity.PASS, Severity.WARN)
