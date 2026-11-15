"""OFFER_ID_VALID — only the eligible offer may appear; no offer talk when none allowed.

Owner: M3. Mandatory -> BLOCK.
"""

from __future__ import annotations

from app.guardrails import extractors as ex
from app.guardrails.base import GuardrailConfig, VerifiedFacts, fields, finding
from app.schemas.generation import RenderedDraft
from app.schemas.validation import Finding, ValidationContext


def _mask(text: str, phrases: list[str]) -> str:
    """Blank out exception phrases (same length, so offsets stay valid)."""
    for s in ex.find_phrases(text, phrases):
        text = text[: s.start] + " " * (s.end - s.start) + text[s.end :]
    return text


class OfferIdValidCheck:
    check_id = "OFFER_ID_VALID"
    mandatory = True

    def __init__(self, config: GuardrailConfig) -> None:
        self._cfg = config

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding]:
        allowed = ctx.llm_input.offer.offer_id.upper() if ctx.llm_input.offer else None
        out = []
        if draft.raw.offer_id is not None and draft.raw.offer_id.upper() != allowed:
            out.append(
                finding(
                    self,
                    f"Draft declares offer_id {draft.raw.offer_id!r}; allowed: {allowed or 'none'}",
                )
            )
        for field, text in fields(draft):
            for s in ex.find_offer_ids(text):
                if s.value != allowed:
                    out.append(
                        finding(self, f"Offer id '{s.text}' is not the eligible offer", field, s)
                    )
            if allowed is None:
                masked = _mask(text, self._cfg.offer_keyword_exceptions)
                for s in ex.find_phrases(masked, self._cfg.offer_keywords):
                    span = ex.Span(text[s.start : s.end], s.start, s.end, s.value)
                    out.append(
                        finding(
                            self,
                            f"Mentions an offer ('{span.text}') but no offer is allowed",
                            field,
                            span,
                        )
                    )
        return out
