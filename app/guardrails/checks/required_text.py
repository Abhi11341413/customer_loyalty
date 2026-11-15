"""DISCLAIMER_PRESENT and SUPPORT_PATH_PRESENT — required text survived (FR-06, §8.5).

Owner: M3. Both mandatory -> BLOCK. These matter most after a reviewer edit.
"""

from __future__ import annotations

from app.guardrails import extractors as ex
from app.guardrails.base import VerifiedFacts, finding
from app.schemas.enums import BILLING_REMINDER_OBJECTIVES
from app.schemas.generation import RenderedDraft
from app.schemas.validation import Finding, ValidationContext


class DisclaimerPresentCheck:
    check_id = "DISCLAIMER_PRESENT"
    mandatory = True

    def __init__(self, known_keys: set[str]) -> None:
        self._known = known_keys

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding]:
        body = ex.normalize_ws(draft.body)
        out = []
        required = ctx.llm_input.required_disclaimers
        unknown = [k for k in required if k not in self._known]
        for key in unknown:
            out.append(finding(self, f"Required disclaimer '{key}' has no approved text"))
        for key, text in zip(
            [k for k in required if k in self._known], facts.disclaimer_texts, strict=True
        ):
            if ex.normalize_ws(text) not in body:
                out.append(
                    finding(self, f"Required disclaimer '{key}' is missing or altered", "body")
                )
        return out


class SupportPathPresentCheck:
    check_id = "SUPPORT_PATH_PRESENT"
    mandatory = True

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding] | None:
        if ctx.llm_input.objective not in BILLING_REMINDER_OBJECTIVES:
            return []
        support = ctx.llm_input.allowed_slots.get("support_path", "").strip()
        if not support:
            return [finding(self, "Billing reminder has no verified support/dispute path (FR-06)")]
        if ex.normalize_ws(support) not in ex.normalize_ws(draft.body):
            return [finding(self, "Support/dispute path is missing from the message", "body")]
        return []
