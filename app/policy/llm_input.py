"""Build minimal LLMInput from decisions (no email, no customer_id).

Owner: M2. Consumer: M3's MessageGenerator (CLAUDE.md §8.4).

The function signature is the privacy control: it never receives an email address,
customer id, consent flags or payment history, so it cannot leak them to the LLM.
"""

from app.policy.config import StrategyConfig
from app.schemas.enums import BILLING_REMINDER_OBJECTIVES, NON_DRAFT_OBJECTIVES
from app.schemas.generation import LLMInput, ToneSpec
from app.schemas.policy import BillingDecision, StrategyDecision


class NotDraftableError(ValueError):
    """The decision does not allow a draft, or a required verified fact is missing."""


def build_llm_input(
    strategy: StrategyDecision,
    *,
    first_name: str,
    billing: BillingDecision | None,
    cfg: StrategyConfig,
    plan_name: str | None = None,
    tone_rules: list[str] | None = None,
) -> LLMInput:
    """Assemble the only context the LLM may see. Raises ``NotDraftableError``, never guesses."""
    if strategy.objective in NON_DRAFT_OBJECTIVES:
        raise NotDraftableError(f"objective {strategy.objective} does not produce a draft")
    if not first_name.strip():
        raise NotDraftableError("first_name is required for the salutation")

    oc = cfg.objectives[strategy.objective]
    slots: dict[str, str] = {"first_name": first_name.strip()}

    if strategy.objective in BILLING_REMINDER_OBJECTIVES:
        if billing is None or not billing.reminder_allowed or not billing.verified_facts:
            raise NotDraftableError("billing reminder without verified billing facts")
        slots.update(billing.verified_facts)

    offer = strategy.allowed_offer
    if offer is not None:
        slots.update(
            offer_title=offer.title,
            offer_value=offer.value_display,
            offer_valid_to=offer.valid_to_display,
            offer_terms=offer.terms_summary,
        )
    if plan_name:
        slots["plan_name"] = plan_name

    cta = cfg.ctas[strategy.cta_key or oc.cta_key]
    slots[cta.slot] = cta.text

    try:
        summary = oc.summary.format_map(slots)
    except KeyError as exc:
        raise NotDraftableError(f"summary needs missing fact {exc}") from exc

    return LLMInput(
        first_name=slots["first_name"],
        objective=strategy.objective,
        segment_summary=summary,
        tone=ToneSpec(name=strategy.tone or oc.tone, rules=list(tone_rules or [])),
        allowed_slots=slots,
        offer=offer,
        required_disclaimers=list(strategy.required_disclaimer_keys),
        template_skeleton=oc.skeleton,
        forbidden=list(cfg.forbidden),
    )
