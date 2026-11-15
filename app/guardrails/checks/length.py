"""LENGTH_LIMITS — body word count (excluding appended disclaimers) within template range.

Owner: M3. Advisory -> WARN.
"""

from __future__ import annotations

from app.generation.content import ContentConfigError, TemplateStore
from app.generation.renderer import split_disclaimers
from app.guardrails.base import VerifiedFacts, finding
from app.schemas.generation import RenderedDraft
from app.schemas.validation import Finding, ValidationContext


class LengthLimitsCheck:
    check_id = "LENGTH_LIMITS"
    mandatory = False

    def __init__(self, templates: TemplateStore) -> None:
        self._templates = templates

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding] | None:
        try:
            lo, hi = self._templates.get(draft.raw.template_id).word_range
        except ContentConfigError:
            return None
        main, _ = split_disclaimers(draft.body)
        words = len(main.split())
        if words < lo:
            return [finding(self, f"Body has {words} words; template minimum is {lo}", "body")]
        if words > hi:
            return [finding(self, f"Body has {words} words; template maximum is {hi}", "body")]
        return []
