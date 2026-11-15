"""TemplateOnly fallback: approved template text with verified slots, no network (§8.7).

Owner: M3.

Deviation from the §3.3 sketch (documented): TemplateOnly is not an ``LLMClient``.
It needs the template id (from StrategyDecision) and the slot set (from LLMInput),
neither of which is in a prompt string, so it produces a ``RawDraft`` directly. It is
always the last step of the generator's chain and cannot fail on valid config.
"""

from __future__ import annotations

from app.generation.content import MessageTemplate, TemplateStore
from app.schemas.generation import FallbackEvent, LLMInput, RawDraft

TEMPLATE_PROVIDER = "template"
TEMPLATE_MODEL_ID = "template-only"


def offer_slot_values(llm_input: LLMInput) -> dict[str, str]:
    """Verified slots derived from the eligible offer (if any)."""
    o = llm_input.offer
    if o is None:
        return {}
    return {
        "offer_title": o.title,
        "offer_value": o.value_display,
        "offer_valid_to": o.valid_to_display,
        "offer_terms": o.terms_summary,
    }


def verified_slot_values(llm_input: LLMInput) -> dict[str, str]:
    """Every slot value the text may use: allowed_slots + offer-derived slots.

    allowed_slots wins if M2 already supplied an offer slot.
    """
    return {**offer_slot_values(llm_input), **llm_input.allowed_slots}


class TemplateOnlyGenerator:
    def __init__(self, templates: TemplateStore) -> None:
        self._templates = templates

    def generate(
        self,
        llm_input: LLMInput,
        template: MessageTemplate,
        fallback_events: list[FallbackEvent] | None = None,
        llm_attempts: int = 0,
    ) -> RawDraft:
        variant = template.select_variant(
            set(verified_slot_values(llm_input)), has_offer=llm_input.offer is not None
        )
        return RawDraft(
            subject=variant.subject,
            body=variant.body,
            objective=llm_input.objective,
            offer_id=llm_input.offer.offer_id if llm_input.offer else None,
            facts_used=sorted(variant.slots),
            disclaimer_keys=list(llm_input.required_disclaimers),
            communication_objective=str(llm_input.objective),
            template_id=template.template_id,
            template_version=template.version,
            prompt_version=None,
            model_provider=TEMPLATE_PROVIDER,
            model_id=TEMPLATE_MODEL_ID,
            fallback_events=list(fallback_events or []),
            llm_attempts=llm_attempts,
        )
