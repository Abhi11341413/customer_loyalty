"""M3 test builders: one realistic LLMInput + StrategyDecision per draft objective.

Owner: M3. Hand-written stand-ins for M2's LLMInput builder (§12: M3 works on
fixtures until app/policy/llm_input.py exists). Values mirror the §16 demo customers.
The same inputs are exported as JSON contract fixtures in tests/fixtures/contracts/.
"""

from __future__ import annotations

from app.generation.clients.template_only import TemplateOnlyGenerator
from app.generation.content import DisclaimerStore, TemplateStore, cta_text
from app.generation.renderer import SlotRenderer
from app.guardrails.runner import GuardrailRunner
from app.schemas.enums import Objective, OfferType
from app.schemas.generation import LLMInput, RawDraft, RenderedDraft, ToneSpec
from app.schemas.policy import StrategyDecision, VerifiedOffer
from app.schemas.validation import ValidationContext

SUPPORT_PATH = "reply to this email or visit the Help section of your account."

OFFER_LOY_200 = VerifiedOffer(
    offer_id="OFF-LOY-200",
    offer_type=OfferType.LOYALTY_REWARD,
    title="Loyalty credit",
    value_display="₹200.00",
    terms_summary="One-time ₹200 bill credit, applied on next bill.",
    valid_to_display="31 Dec 2026",
)
OFFER_RE_5GB = VerifiedOffer(
    offer_id="OFF-RE-5GB",
    offer_type=OfferType.REENGAGEMENT,
    title="5 GB bonus data",
    value_display="5 GB",
    terms_summary="5 GB bonus data valid for 30 days after activation.",
    valid_to_display="31 Dec 2026",
)

_MARKETING_DISCLAIMERS = ["unsubscribe"]
_OFFER_DISCLAIMERS = ["offer_terms", "unsubscribe"]
_BILLING_DISCLAIMERS = ["already_paid", "support_dispute_path"]

# objective -> (template_id, tone, cta_key, first_name, extra slots, offer, disclaimers)
_CASES: dict[Objective, tuple] = {
    Objective.APPRECIATION: (
        "appreciation_v1", "warm_grateful", "explore_account", "Mei",
        {"plan_name": "Postpaid 599"}, None, _MARKETING_DISCLAIMERS,
    ),
    Objective.LOYALTY_REWARD: (
        "loyalty_reward_v1", "warm_celebratory", "view_reward", "Asha",
        {"plan_name": "Postpaid 499"}, OFFER_LOY_200, _OFFER_DISCLAIMERS,
    ),
    Objective.REENGAGEMENT: (
        "reengagement_declining_v1", "helpful_low_pressure", "view_plan", "Arjun",
        {"plan_name": "Postpaid 499"}, OFFER_RE_5GB, _OFFER_DISCLAIMERS,
    ),
    Objective.WINBACK: (
        "winback_dormant_v1", "friendly_no_guilt", "reactivate", "Lena",
        {}, OFFER_RE_5GB, _OFFER_DISCLAIMERS,
    ),
    Objective.BILLING_REMINDER_COURTEOUS: (
        "billing_reminder_stage1", "courteous", "pay_bill", "Ravi",
        {"amount_due": "₹599.00", "due_date": "10 Nov 2026", "bill_period": "October 2026",
         "support_path": SUPPORT_PATH},
        None, _BILLING_DISCLAIMERS,
    ),
    Objective.BILLING_REMINDER_FOLLOWUP: (
        "billing_reminder_stage2", "polite_clear", "pay_bill", "Kiran",
        {"amount_due": "₹499.00", "due_date": "3 Nov 2026", "bill_period": "October 2026",
         "support_path": SUPPORT_PATH},
        None, _BILLING_DISCLAIMERS,
    ),
    Objective.BILLING_REMINDER_FIRM: (
        "billing_reminder_stage3", "firm_respectful", "pay_or_contact", "Omar",
        {"amount_due": "₹749.00", "due_date": "20 Oct 2026", "bill_period": "September 2026",
         "days_overdue": "26", "support_path": SUPPORT_PATH},
        None, [*_BILLING_DISCLAIMERS, "need_help"],
    ),
}  # fmt: skip

DRAFT_OBJECTIVES = list(_CASES)


def llm_input(objective: Objective, **overrides) -> LLMInput:
    template_id, tone, cta_key, name, extra, offer, disclaimers = _CASES[objective]
    data = dict(
        first_name=name,
        objective=objective,
        segment_summary=f"Demo case for {objective}",
        tone=ToneSpec(name=tone, rules=["be respectful"]),
        allowed_slots={"first_name": name, "cta": cta_text(cta_key), **extra},
        offer=offer,
        required_disclaimers=list(disclaimers),
        template_skeleton="greeting -> reason for writing -> facts -> CTA -> sign-off",
        forbidden=["threats", "fees not provided"],
    )
    data.update(overrides)
    return LLMInput(**data)


def strategy(objective: Objective, **overrides) -> StrategyDecision:
    template_id, tone, cta_key, _n, _e, offer, disclaimers = _CASES[objective]
    data = dict(
        objective=objective,
        template_id=template_id,
        template_version="1.0",
        tone=tone,
        allowed_offer=offer,
        required_disclaimer_keys=list(disclaimers),
        cta_key=cta_key,
    )
    data.update(overrides)
    return StrategyDecision(**data)


_TEMPLATES: TemplateStore | None = None
_RENDERER: SlotRenderer | None = None
_RUNNER: GuardrailRunner | None = None


def templates() -> TemplateStore:
    global _TEMPLATES
    if _TEMPLATES is None:
        _TEMPLATES = TemplateStore()
    return _TEMPLATES


def renderer() -> SlotRenderer:
    global _RENDERER
    if _RENDERER is None:
        _RENDERER = SlotRenderer(DisclaimerStore())
    return _RENDERER


def runner() -> GuardrailRunner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = GuardrailRunner.default(templates())
    return _RUNNER


def template_raw(objective: Objective, li: LLMInput | None = None) -> RawDraft:
    li = li or llm_input(objective)
    return TemplateOnlyGenerator(templates()).generate(li, templates().get(_CASES[objective][0]))


def rendered(objective: Objective, li: LLMInput | None = None) -> RenderedDraft:
    li = li or llm_input(objective)
    return renderer().render(template_raw(objective, li), li)


def ctx(objective: Objective, li: LLMInput | None = None, **kw) -> ValidationContext:
    return ValidationContext(llm_input=li or llm_input(objective), **kw)


def good_llm_reply(objective: Objective) -> dict:
    """A schema-valid, policy-clean reply the way a real LLM would write it."""
    li = llm_input(objective)
    raw = template_raw(objective, li)
    return {
        "subject": raw.subject,
        "body": raw.body.replace("Thank you,", "Many thanks,"),
        "customer_segment": "demo",
        "communication_objective": str(objective),
        "facts_used": raw.facts_used,
        "offer_id": li.offer.offer_id if li.offer else None,
        "disclaimer_keys": list(li.required_disclaimers),
    }
