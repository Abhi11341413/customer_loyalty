"""StrategySelector (FR-03): segments + decisions -> one objective/template/tone.

Owner: M2. Deterministic, no LLM import (CLAUDE.md §7).

Principle: one message, one objective. Precedence (highest first):

    ESCALATE > NO_CONTACT_BY_POLICY > BILLING_REMINDER > engagement rules > NO_CONTACT

Two pure steps so the orchestrator (M4) can ask the contact gate about the *chosen*
category/objective in between::

    plan     = select_strategy(segments, billing, offers, strategy_cfg)
    contact  = check_contact(prefs, status, history, plan.category, plan.objective, ...)
    decision = apply_contact(plan, contact)

``apply_contact`` is a no-op for ESCALATE / NO_CONTACT (no category to check).
"""

from collections.abc import Iterable

from app.policy.config import StrategyConfig
from app.schemas.enums import BillState, Objective, Segment
from app.schemas.policy import (
    BillingDecision,
    ContactDecision,
    OfferDecision,
    StrategyDecision,
    SuppressedObjective,
    VerifiedOffer,
)

# Rationale codes
STRATEGY_BILLING_ESCALATION = "STRATEGY_BILLING_ESCALATION"
STRATEGY_SEGMENT_ESCALATION = "STRATEGY_SEGMENT_ESCALATION"
STRATEGY_BILLING_PRIORITY = "STRATEGY_BILLING_PRIORITY"
STRATEGY_REMINDER_NOT_ALLOWED = "STRATEGY_REMINDER_NOT_ALLOWED"
STRATEGY_NO_ELIGIBLE_OFFER = "STRATEGY_NO_ELIGIBLE_OFFER"
STRATEGY_NO_TARGET_PATTERN = "STRATEGY_NO_TARGET_PATTERN"
STRATEGY_CONTACT_REFUSED = "STRATEGY_CONTACT_REFUSED"

_OVERDUE_STATES = frozenset({BillState.OVERDUE, BillState.PARTIALLY_PAID_OVERDUE})


def _engagement_objective(segments: frozenset[Segment], cfg: StrategyConfig) -> Objective | None:
    for rule in cfg.engagement_rules:
        if set(rule.when_all) <= segments:
            return rule.objective
    return None


def _pick_offer(
    objective: Objective, offers: OfferDecision, cfg: StrategyConfig
) -> VerifiedOffer | None:
    """First eligible offer (by offer_id, deterministic) whose type the objective allows."""
    allowed = set(cfg.objectives[objective].allowed_offer_types)
    candidates = sorted(
        (e.offer for e in offers.eligible if e.offer is not None and e.offer.offer_type in allowed),
        key=lambda o: o.offer_id,
    )
    return candidates[0] if candidates else None


def _build(
    objective: Objective,
    cfg: StrategyConfig,
    *,
    offer: VerifiedOffer | None = None,
    stage: int | None = None,
    suppressed: list[SuppressedObjective] | None = None,
    rationale: list[str] | None = None,
) -> StrategyDecision:
    oc = cfg.objectives[objective]
    disclaimers = list(oc.disclaimers) + (list(oc.offer_disclaimers) if offer else [])
    return StrategyDecision(
        objective=objective,
        category=oc.category,
        template_id=oc.template_id,
        template_version=oc.template_version,
        tone=oc.tone,
        allowed_offer=offer,
        required_disclaimer_keys=list(dict.fromkeys(disclaimers)),
        cta_key=oc.cta_key,
        reminder_stage=stage,
        suppressed=suppressed or [],
        rationale_codes=rationale or [],
    )


def _no_draft(
    objective: Objective, rationale: list[str], suppressed: list[SuppressedObjective] | None = None
) -> StrategyDecision:
    return StrategyDecision(
        objective=objective, rationale_codes=rationale, suppressed=suppressed or []
    )


def select_strategy(
    segments: Iterable[Segment],
    billing: BillingDecision,
    offers: OfferDecision,
    cfg: StrategyConfig,
) -> StrategyDecision:
    """Resolve segments + billing + offers into one candidate objective (before contact)."""
    segs = frozenset(segments)
    engagement = _engagement_objective(segs, cfg)

    # 1. Escalation: uncertain billing data, disputes, or not enough data to classify.
    if billing.escalate:
        return _no_draft(Objective.ESCALATE, [STRATEGY_BILLING_ESCALATION, *billing.reason_codes])
    escalating = sorted(s.value for s in segs & set(cfg.escalate_segments))
    if escalating:
        return _no_draft(Objective.ESCALATE, [STRATEGY_SEGMENT_ESCALATION, *escalating])

    # 2. Billing first: an overdue bill outranks every marketing objective (§7.3, D9).
    if billing.state in _OVERDUE_STATES:
        suppressed = (
            [SuppressedObjective(objective=engagement, reason_codes=[STRATEGY_BILLING_PRIORITY])]
            if engagement
            else []
        )
        if not billing.reminder_allowed or billing.stage is None:
            return _no_draft(
                Objective.NO_CONTACT,
                [STRATEGY_REMINDER_NOT_ALLOWED, *billing.reason_codes],
                suppressed,
            )
        objective = cfg.billing_stage_objectives[billing.stage]
        return _build(
            objective,
            cfg,
            stage=billing.stage,
            suppressed=suppressed,
            rationale=list(billing.reason_codes),
        )

    # 3. Engagement objectives.
    if engagement is None:
        return _no_draft(Objective.NO_CONTACT, [STRATEGY_NO_TARGET_PATTERN])

    suppressed: list[SuppressedObjective] = []
    offer = _pick_offer(engagement, offers, cfg)
    oc = cfg.objectives[engagement]
    if oc.offer_required and offer is None:
        suppressed.append(
            SuppressedObjective(objective=engagement, reason_codes=[STRATEGY_NO_ELIGIBLE_OFFER])
        )
        engagement = oc.fallback_objective  # validated non-None at config load
        assert engagement is not None
        offer = _pick_offer(engagement, offers, cfg)
    return _build(
        engagement,
        cfg,
        offer=offer,
        suppressed=suppressed,
        rationale=[f"SEGMENTS:{','.join(sorted(s.value for s in segs))}"],
    )


def apply_contact(plan: StrategyDecision, contact: ContactDecision | None) -> StrategyDecision:
    """Final decision: a refused contact wins over everything except ESCALATE."""
    if plan.category is None or contact is None or contact.allowed:
        return plan
    return StrategyDecision(
        objective=Objective.NO_CONTACT_BY_POLICY,
        category=plan.category,
        suppressed=[
            SuppressedObjective(objective=plan.objective, reason_codes=list(contact.reasons)),
            *plan.suppressed,
        ],
        rationale_codes=[STRATEGY_CONTACT_REFUSED, *contact.reasons],
    )
