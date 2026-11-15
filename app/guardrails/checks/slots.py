"""UNKNOWN_SLOT — every placeholder was filled with a verified value.

Owner: M3. Mandatory -> BLOCK.
"""

from __future__ import annotations

import re

from app.generation.content import SLOT_RE
from app.guardrails.base import VerifiedFacts, fields, finding
from app.guardrails.extractors import Span
from app.schemas.generation import RenderedDraft
from app.schemas.validation import Finding, ValidationContext

_STRAY_BRACES = re.compile(r"\{\{|\}\}")


class UnknownSlotCheck:
    check_id = "UNKNOWN_SLOT"
    mandatory = True

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding]:
        out: list[Finding] = []
        seen: set[str] = set()
        for field, text in fields(draft):
            for m in SLOT_RE.finditer(text):
                seen.add(m.group(1))
                out.append(
                    finding(
                        self,
                        f"Slot {{{{{m.group(1)}}}}} is not a verified fact for this message",
                        field,
                        Span(m.group(0), m.start(), m.end(), m.group(1)),
                    )
                )
            if not SLOT_RE.search(text):
                for m in _STRAY_BRACES.finditer(text):
                    out.append(
                        finding(
                            self,
                            "Malformed placeholder braces",
                            field,
                            Span(m.group(0), m.start(), m.end(), None),
                        )
                    )
        for name in draft.unknown_slots:
            if name not in seen:
                out.append(finding(self, f"Slot {{{{{name}}}}} was not provided"))
        return out
