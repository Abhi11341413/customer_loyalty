"""SCHEMA_VALID — draft structure is intact and echoes the requested objective.

Owner: M3. Mandatory -> BLOCK.
"""

from __future__ import annotations

from app.guardrails.base import VerifiedFacts, finding
from app.schemas.generation import RenderedDraft
from app.schemas.validation import Finding, ValidationContext

MAX_SUBJECT_CHARS = 120  # rendered subject (slots filled) may exceed the 90-char raw limit


class SchemaValidCheck:
    check_id = "SCHEMA_VALID"
    mandatory = True

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding]:
        out: list[Finding] = []
        objective = str(ctx.llm_input.objective)
        if draft.raw.objective != ctx.llm_input.objective:
            out.append(finding(self, f"Draft objective {draft.raw.objective} != {objective}"))
        if draft.raw.communication_objective != objective:
            out.append(
                finding(
                    self,
                    f"communication_objective echoed {draft.raw.communication_objective!r}, "
                    f"expected {objective!r}",
                )
            )
        if not draft.subject.strip():
            out.append(finding(self, "Subject is empty", "subject"))
        elif len(draft.subject) > MAX_SUBJECT_CHARS:
            out.append(finding(self, f"Subject longer than {MAX_SUBJECT_CHARS} chars", "subject"))
        if not draft.body.strip():
            out.append(finding(self, "Body is empty", "body"))
        return out
