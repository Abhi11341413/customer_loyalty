"""AMOUNT_GROUNDED, DATE_GROUNDED, NUMBER_GROUNDED — every factual token is verified.

Owner: M3. All mandatory -> BLOCK (§8.3: "don't hallucinate facts" as a check).

The allow-list is built only from LLMInput (allowed slots, the eligible offer and the
approved disclaimer text), never from the draft itself.
"""

from __future__ import annotations

from app.guardrails import extractors as ex
from app.guardrails.base import VerifiedFacts, fields, finding
from app.schemas.generation import RenderedDraft
from app.schemas.validation import Finding, ValidationContext


class AmountGroundedCheck:
    check_id = "AMOUNT_GROUNDED"
    mandatory = True

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding]:
        out = []
        for field, text in fields(draft):
            for s in ex.find_money(text):
                if s.value not in facts.money:
                    out.append(
                        finding(self, f"Amount '{s.text}' is not a verified value", field, s)
                    )
        return out


class DateGroundedCheck:
    check_id = "DATE_GROUNDED"
    mandatory = True

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding]:
        out = []
        for field, text in fields(draft):
            for s in ex.find_dates(text):
                if isinstance(s.value, ex.DateValue):
                    if not any(s.value.matches(v) for v in facts.dates):
                        out.append(
                            finding(self, f"Date '{s.text}' is not a verified value", field, s)
                        )
                elif not facts.contains_text(s.text):
                    out.append(
                        finding(
                            self, f"Deadline/relative time '{s.text}' is not in the input", field, s
                        )
                    )
        return out


class NumberGroundedCheck:
    check_id = "NUMBER_GROUNDED"
    mandatory = True

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding]:
        out = []
        for field, text in fields(draft):
            for s in ex.find_unit_numbers(text):
                number, _unit = s.value
                if s.value in facts.unit_numbers or number in facts.bare_numbers:
                    continue
                out.append(finding(self, f"Number '{s.text}' is not a verified value", field, s))
        return out
