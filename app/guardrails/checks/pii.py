"""PII_LEAKAGE — no contact details, card/ID numbers, internal ids/codes, other names.

Owner: M3. Mandatory -> BLOCK.

Spans that appear verbatim in a verified value (e.g. a helpline inside support_path)
are allowed. Reviewer edits are re-validated with this same check, which is how
SENSITIVE_INPUT (§9.2) is enforced.
"""

from __future__ import annotations

import re

from app.guardrails import extractors as ex
from app.guardrails.base import GuardrailConfig, VerifiedFacts, fields, finding
from app.schemas.generation import RenderedDraft
from app.schemas.validation import Finding, ValidationContext


class PiiLeakageCheck:
    check_id = "PII_LEAKAGE"
    mandatory = True

    def __init__(self, config: GuardrailConfig) -> None:
        prefixes = "|".join(re.escape(p) for p in config.internal_code_prefixes)
        terms = "|".join(re.escape(t) for t in config.internal_terms)
        # Case-sensitive on purpose: "CONSISTENT" is an internal label, "consistent" is prose.
        self._internal = re.compile(rf"\b(?:(?:{prefixes})[A-Z0-9_]+|{terms})\b")

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding]:
        out = []
        for field, text in fields(draft):
            for s in ex.find_pii(text):
                if not facts.contains_text(s.text):
                    out.append(finding(self, f"Sensitive data ({s.value}): '{s.text}'", field, s))
            for m in self._internal.finditer(text):
                span = ex.Span(m.group(0), m.start(), m.end(), "INTERNAL_CODE")
                out.append(
                    finding(self, f"Internal code/segment name leaked: '{m.group(0)}'", field, span)
                )
        greet = ex.salutation_name(draft.body)
        if greet and greet.text.lower() != ctx.llm_input.first_name.strip().lower():
            out.append(
                finding(self, f"Greeting addresses '{greet.text}', not the customer", "body", greet)
            )
        return out
