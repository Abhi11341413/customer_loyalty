"""BLOCKED_LANGUAGE (mandatory), FACT_CONTRADICTION (mandatory), TONE_KEYWORDS (advisory).

Owner: M3. Lexicons in config/policies/blocked_language.yaml.
"""

from __future__ import annotations

from app.guardrails import extractors as ex
from app.guardrails.base import GuardrailConfig, VerifiedFacts, fields, finding
from app.schemas.enums import BILLING_REMINDER_OBJECTIVES
from app.schemas.generation import RenderedDraft
from app.schemas.validation import Finding, ValidationContext


class BlockedLanguageCheck:
    check_id = "BLOCKED_LANGUAGE"
    mandatory = True

    def __init__(self, config: GuardrailConfig) -> None:
        self._terms_by_cat: dict[str, list[str]] = dict(config.always_blocked)

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding]:
        out = []
        for field, text in fields(draft):
            for category, terms in self._terms_by_cat.items():
                for s in ex.find_phrases(text, terms):
                    out.append(
                        finding(self, f"Prohibited language ({category}): '{s.text}'", field, s)
                    )
        return out


class FactContradictionCheck:
    check_id = "FACT_CONTRADICTION"
    mandatory = True

    def __init__(self, config: GuardrailConfig) -> None:
        self._cfg = config

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding]:
        is_billing = ctx.llm_input.objective in BILLING_REMINDER_OBJECTIVES
        key = "billing_reminder_forbids" if is_billing else "non_billing_forbids"
        why = (
            "claims the bill is paid, but this is an overdue reminder"
            if is_billing
            else "mentions billing status, but this is not a billing message"
        )
        out = []
        for field, text in fields(draft):
            for s in ex.find_phrases(text, self._cfg.contradiction.get(key, [])):
                out.append(finding(self, f"'{s.text}' {why}", field, s))
        return out


class ToneKeywordsCheck:
    check_id = "TONE_KEYWORDS"
    mandatory = False

    def __init__(self, config: GuardrailConfig) -> None:
        self._cfg = config

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding]:
        objective = str(ctx.llm_input.objective)
        lexicons = []
        if objective in self._cfg.pressure_terms_warn_in:
            lexicons.append(("pressure/urgency", self._cfg.pressure_terms))
        if objective in self._cfg.casual_terms_warn_in:
            lexicons.append(("too casual for a firm notice", self._cfg.casual_terms))
        out = []
        for field, text in fields(draft):
            for label, terms in lexicons:
                for s in ex.find_phrases(text, terms):
                    if facts.contains_text(s.text):  # e.g. "exclusive" in the offer title
                        continue
                    out.append(finding(self, f"Tone: '{s.text}' ({label})", field, s))
        return out
