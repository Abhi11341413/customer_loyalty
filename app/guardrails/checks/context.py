"""Checks driven by state the orchestrator supplies in ValidationContext.

Owner: M3.
- CONSENT_STILL_VALID (mandatory -> BLOCK): ContactPolicyGate re-run says no.
- DUPLICATE_OUTREACH (mandatory -> BLOCK): another draft pending/delivered in window.
- LOW_CONFIDENCE_SEGMENT (advisory -> WARN): LOW band or shadow-model disagreement.
Each returns None (skipped) when the context field was not supplied.
"""

from __future__ import annotations

from app.guardrails.base import VerifiedFacts, finding
from app.schemas.enums import ConfidenceBand
from app.schemas.generation import RenderedDraft
from app.schemas.validation import Finding, ValidationContext


class ConsentStillValidCheck:
    check_id = "CONSENT_STILL_VALID"
    mandatory = True

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding] | None:
        if ctx.contact_allowed is None:
            return None
        if ctx.contact_allowed:
            return []
        reasons = ", ".join(ctx.contact_reasons) or "contact not allowed"
        return [finding(self, f"Customer can no longer be contacted: {reasons}")]


class DuplicateOutreachCheck:
    check_id = "DUPLICATE_OUTREACH"
    mandatory = True

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding] | None:
        if ctx.duplicate_outreach is None:
            return None
        if not ctx.duplicate_outreach:
            return []
        return [
            finding(self, "Another message with this objective is pending or was recently sent")
        ]


class LowConfidenceSegmentCheck:
    check_id = "LOW_CONFIDENCE_SEGMENT"
    mandatory = False

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding] | None:
        if ctx.confidence_band is None and ctx.shadow_agrees is None:
            return None
        out = []
        if ctx.confidence_band is ConfidenceBand.LOW:
            out.append(finding(self, "Borderline segment: classification confidence is LOW"))
        if ctx.shadow_agrees is False:
            out.append(finding(self, "Advisory shadow model disagrees with the rule-based segment"))
        return out
