"""TEMPORARY scripted placeholders for components owned by M1, M2 and M3.

Owner: M4. Enabled only when PIPELINE_STUBS=true. Delete this module once the real
ProfileAssembler/FeatureBuilder/SegmentationEngine (M1), policy engines (M2) and
generator/renderer/guardrails (M3) are wired in `app/core/container.py`.

What this is: the ten fixed demo customers from blueprint section 16 with *pre-decided*
classification, billing, offer and strategy outcomes, a template-only text generator, and a
deliberately small guardrail set. It exists so the M4 parts (API, orchestrator, review state
machine, delivery gate, audit, UI) can be built and demonstrated before CP1/CP2.

What this is not: the real business rules. Nothing here is computed from data, and the
guardrails are a minimal stand-in; M3's GuardrailRunner replaces them. Review, approval and
the delivery gate are NOT stubbed: they run the real M4 code against whatever these return.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date

from app.core.errors import CustomerNotFoundError
from app.schemas.classification import ClassificationResult, ReasonCode
from app.schemas.customer import (
    CommRecord,
    ContactPreferences,
    CustomerFeatures,
    CustomerPlan,
    CustomerProfile,
)
from app.schemas.enums import (
    BillState,
    ConfidenceBand,
    EngagementSegment,
    MessageCategory,
    Objective,
    Segment,
    Severity,
)
from app.schemas.generation import GenerationMeta, LLMInput, RawDraft, RenderedDraft, ToneSpec
from app.schemas.policy import (
    BillingDecision,
    ContactDecision,
    OfferDecision,
    OfferEvaluation,
    StrategyDecision,
    SuppressedObjective,
    VerifiedOffer,
)
from app.schemas.validation import Finding, ValidationContext, ValidationReport, aggregate_severity

STUB_VERSION = "stub-0.1"
SUPPORT_PATH = (
    "reply to this email or visit the Help section of your account to ask a question "
    "or raise a dispute."
)

# ---------------------------------------------------------------------------------------
# Demo scenario data (synthetic; mirrors blueprint section 16)
# ---------------------------------------------------------------------------------------
OFF_LOY_200 = VerifiedOffer(
    offer_id="OFF-LOY-200",
    offer_type="LOYALTY_REWARD",
    title="Loyalty credit",
    value_display="₹200 bill credit",
    terms_summary="One-time ₹200 bill credit, applied on your next bill.",
    valid_to_display="31 Dec 2026",
)
OFF_RE_5GB = VerifiedOffer(
    offer_id="OFF-RE-5GB",
    offer_type="REENGAGEMENT",
    title="Bonus data",
    value_display="5 GB bonus data",
    terms_summary="5 GB of bonus data added to your current plan.",
    valid_to_display="31 Dec 2026",
)


def _ok(offer: VerifiedOffer) -> OfferEvaluation:
    return OfferEvaluation(offer_id=offer.offer_id, eligible=True, offer=offer)


def _no(offer_id: str, *codes: str) -> OfferEvaluation:
    return OfferEvaluation(offer_id=offer_id, eligible=False, failed_checks=list(codes))


def _overdue(
    stage: int, bill: str, amount: str, due: str, period: str, days: int
) -> BillingDecision:
    return BillingDecision(
        state=BillState.OVERDUE,
        reminder_allowed=True,
        stage=stage,
        bill_id=bill,
        verified_facts={
            "bill_period": period,
            "amount_due": amount,
            "original_amount": amount,
            "due_date": due,
            "days_overdue": str(days),
        },
        reason_codes=[f"BILL_OVERDUE_DAYS:{days}", f"BILL_STAGE:{stage}"],
    )


PAID = BillingDecision(state=BillState.PAID, reminder_allowed=False)
CONSENT_ALL = ContactPreferences(
    email_service_consent=True,
    email_marketing_consent=True,
    email_opt_out=False,
    preferred_channel="EMAIL",
)


@dataclass(frozen=True)
class Scenario:
    first_name: str
    customer_since: date
    plan_name: str
    engagement: EngagementSegment
    reasons: list[tuple[str, str]]
    confidence: float
    objective: Objective  # what strategy would pick if contact is allowed
    billing: BillingDecision = PAID
    offers: OfferDecision = field(default_factory=OfferDecision)
    loyalty: bool = False
    preferences: ContactPreferences = CONSENT_ALL
    adversarial: bool = False  # C0008: scripted unsafe "LLM" output


SCENARIOS: dict[str, Scenario] = {
    "C0001": Scenario(
        "Meera",
        date(2026, 3, 2),
        "Postpaid 499",
        EngagementSegment.CONSISTENT,
        [
            ("ENG_ACTIVE_MONTHS", "Active 6 of the last 6 months."),
            ("ENG_STABLE_USAGE", "Monthly usage is stable (variation 0.18, threshold 0.5)."),
            ("PAY_ON_TIME_RATE", "100% of bills paid on time in the last 12 months (8/8)."),
        ],
        0.88,
        Objective.APPRECIATION,
        offers=OfferDecision(
            rejected=[_no("OFF-LOY-200", "OFFER_SEGMENT_INELIGIBLE", "OFFER_TENURE_SHORT")]
        ),
    ),
    "C0002": Scenario(
        "Asha",
        date(2024, 4, 10),
        "Postpaid 499",
        EngagementSegment.CONSISTENT,
        [
            ("ENG_ACTIVE_MONTHS", "Active 6 of the last 6 months."),
            ("LOY_TENURE_MONTHS", "Customer for 31 months (threshold 12)."),
            ("LOY_PERFECT_RECENT_PAYMENTS", "No late payments in the last 6 months."),
            ("PAY_ON_TIME_RATE", "100% of bills paid on time in the last 12 months."),
        ],
        0.91,
        Objective.LOYALTY_REWARD,
        loyalty=True,
        offers=OfferDecision(
            eligible=[_ok(OFF_LOY_200)], rejected=[_no("OFF-LOY-OLD", "OFFER_EXPIRED")]
        ),
    ),
    "C0003": Scenario(
        "Daniel",
        date(2025, 1, 15),
        "Prepaid 299",
        EngagementSegment.DECLINING_ACTIVITY,
        [
            (
                "ENG_ACTIVITY_DROP_PCT",
                "Average monthly activity fell 65% (40.0 -> 14.0) versus the prior 3 months; "
                "threshold is 30%.",
            ),
            ("ENG_PRIOR_BASELINE", "Prior 3-month average was 40.0 events (minimum 5)."),
        ],
        0.84,
        Objective.REENGAGEMENT,
        offers=OfferDecision(eligible=[_ok(OFF_RE_5GB)]),
    ),
    "C0004": Scenario(
        "Farah",
        date(2024, 9, 1),
        "Prepaid 299",
        EngagementSegment.DORMANT,
        [("ENG_INACTIVE_DAYS", "No activity for 92 days (threshold 60).")],
        0.93,
        Objective.WINBACK,
        offers=OfferDecision(eligible=[_ok(OFF_RE_5GB)]),
    ),
    "C0005": Scenario(
        "Ravi",
        date(2025, 6, 20),
        "Postpaid 599",
        EngagementSegment.CONSISTENT,
        [
            ("ENG_ACTIVE_MONTHS", "Active 6 of the last 6 months."),
            ("BILL_OVERDUE_DAYS", "Bill for October 2026 is 5 days overdue (stage 1: 1-10 days)."),
        ],
        0.86,
        Objective.BILLING_REMINDER_COURTEOUS,
        billing=_overdue(1, "B-C0005-2026-10", "₹599.00", "10 Nov 2026", "October 2026", 5),
        offers=OfferDecision(
            rejected=[_no("OFF-RE-5GB", "OFFER_SEGMENT_INELIGIBLE", "OFFER_BLOCKED_BY_BILLING")]
        ),
    ),
    "C0006": Scenario(
        "Kenji",
        date(2023, 11, 5),
        "Postpaid 749",
        EngagementSegment.STANDARD,
        [
            ("ENG_NO_TARGET_PATTERN", "Active but no targeted engagement pattern."),
            ("BILL_OVERDUE_DAYS", "Bill for September 2026 is 26 days overdue (stage 3: 21-60)."),
            ("BILL_PRIOR_REMINDERS", "Stage 1 sent 22 days ago, stage 2 sent 9 days ago."),
        ],
        0.80,
        Objective.BILLING_REMINDER_FIRM,
        billing=_overdue(3, "B-C0006-2026-09", "₹749.00", "20 Oct 2026", "September 2026", 26),
    ),
    "C0007": Scenario(
        "Lucia",
        date(2023, 2, 14),
        "Postpaid 499",
        EngagementSegment.CONSISTENT,
        [
            ("ENG_ACTIVE_MONTHS", "Active 6 of the last 6 months."),
            ("LOY_TENURE_MONTHS", "Customer for 45 months (threshold 12)."),
        ],
        0.90,
        Objective.LOYALTY_REWARD,
        loyalty=True,
        offers=OfferDecision(eligible=[_ok(OFF_LOY_200)]),
        preferences=ContactPreferences(
            email_service_consent=False,
            email_marketing_consent=False,
            email_opt_out=True,
            preferred_channel="NONE",
        ),
    ),
    "C0008": Scenario(
        "Omar",
        date(2025, 2, 3),
        "Prepaid 299",
        EngagementSegment.DECLINING_ACTIVITY,
        [
            (
                "ENG_ACTIVITY_DROP_PCT",
                "Average monthly activity fell 58% (31.0 -> 13.0) versus the prior 3 months; "
                "threshold is 30%.",
            )
        ],
        0.79,
        Objective.REENGAGEMENT,
        adversarial=True,
        offers=OfferDecision(eligible=[_ok(OFF_RE_5GB)]),
    ),
    "C0009": Scenario(
        "Priya",
        date(2024, 1, 22),
        "Postpaid 599",
        EngagementSegment.CONSISTENT,
        [
            ("LOY_TENURE_MONTHS", "Customer for 33 months (threshold 12)."),
            ("BILL_OVERDUE_DAYS", "Bill for October 2026 is 12 days overdue (stage 2: 11-20)."),
            ("BILL_PRIOR_REMINDERS", "Stage 1 reminder sent 8 days ago."),
        ],
        0.85,
        Objective.BILLING_REMINDER_FOLLOWUP,
        loyalty=True,
        billing=_overdue(2, "B-C0009-2026-10", "₹599.00", "3 Nov 2026", "October 2026", 12),
        offers=OfferDecision(rejected=[_no("OFF-LOY-200", "OFFER_BLOCKED_BY_BILLING")]),
    ),
    "C0010": Scenario(
        "Tomas",
        date(2024, 7, 30),
        "Postpaid 599",
        EngagementSegment.CONSISTENT,
        [("BILL_DISPUTED", "The October 2026 bill has an open dispute; reminders suppressed.")],
        0.82,
        Objective.ESCALATE,
        billing=BillingDecision(
            state=BillState.DISPUTED,
            reminder_allowed=False,
            escalate=True,
            bill_id="B-C0010-2026-10",
            reason_codes=["BILL_DISPUTED"],
        ),
        offers=OfferDecision(rejected=[_no("OFF-LOY-200", "OFFER_BLOCKED_BY_BILLING")]),
    ),
}

STRATEGY_TABLE: dict[Objective, dict] = {
    Objective.APPRECIATION: dict(
        category=MessageCategory.MARKETING,
        template_id="appreciation_v1",
        tone="warm_grateful",
        disclaimers=["unsubscribe"],
        cta="account_cta",
        offer_types=["APPRECIATION_PERK"],
    ),
    Objective.LOYALTY_REWARD: dict(
        category=MessageCategory.MARKETING,
        template_id="loyalty_reward_v1",
        tone="warm_celebratory",
        disclaimers=["offer_terms", "unsubscribe"],
        cta="reward_cta",
        offer_types=["LOYALTY_REWARD"],
    ),
    Objective.REENGAGEMENT: dict(
        category=MessageCategory.MARKETING,
        template_id="reengagement_declining_v1",
        tone="helpful_low_pressure",
        disclaimers=["offer_terms", "unsubscribe"],
        cta="plan_cta",
        offer_types=["REENGAGEMENT"],
    ),
    Objective.WINBACK: dict(
        category=MessageCategory.MARKETING,
        template_id="winback_dormant_v1",
        tone="friendly_no_guilt",
        disclaimers=["offer_terms", "unsubscribe"],
        cta="return_cta",
        offer_types=["REENGAGEMENT"],
    ),
    Objective.BILLING_REMINDER_COURTEOUS: dict(
        category=MessageCategory.SERVICE,
        template_id="billing_reminder_stage1",
        tone="courteous",
        disclaimers=["already_paid", "support_dispute_path"],
        cta="pay_cta",
        offer_types=[],
    ),
    Objective.BILLING_REMINDER_FOLLOWUP: dict(
        category=MessageCategory.SERVICE,
        template_id="billing_reminder_stage2",
        tone="polite_follow_up",
        disclaimers=["already_paid", "support_dispute_path"],
        cta="pay_cta",
        offer_types=[],
    ),
    Objective.BILLING_REMINDER_FIRM: dict(
        category=MessageCategory.SERVICE,
        template_id="billing_reminder_stage3",
        tone="firm_respectful",
        disclaimers=["already_paid", "support_dispute_path"],
        cta="pay_cta",
        offer_types=[],
    ),
}
BILLING_OBJECTIVES = {
    Objective.BILLING_REMINDER_COURTEOUS,
    Objective.BILLING_REMINDER_FOLLOWUP,
    Objective.BILLING_REMINDER_FIRM,
}


def _scenario(customer_id: str) -> Scenario:
    try:
        return SCENARIOS[customer_id]
    except KeyError:
        raise CustomerNotFoundError(
            "Customer not found.", details={"customer_id": customer_id}
        ) from None


# ---------------------------------------------------------------------------------------
# M1 placeholders
# ---------------------------------------------------------------------------------------
class StubProfileAssembler:
    def assemble(self, customer_id: str, as_of: date) -> CustomerProfile:
        s = _scenario(customer_id)
        return CustomerProfile(
            customer_id=customer_id,
            as_of_date=as_of,
            first_name=s.first_name,
            email=f"{s.first_name.lower()}.{customer_id.lower()}@example.test",
            customer_since=s.customer_since,
            account_status="ACTIVE",
            preferences=s.preferences,
            plans=[
                CustomerPlan(
                    plan_id="PL-" + s.plan_name.upper().replace(" ", "-"),
                    plan_name=s.plan_name,
                    plan_category="POSTPAID" if s.plan_name.startswith("Post") else "PREPAID",
                    start_date=s.customer_since,
                    status="ACTIVE",
                )
            ],
        )


class StubFeatureBuilder:
    def build(self, profile: CustomerProfile) -> CustomerFeatures:
        s = _scenario(profile.customer_id)
        days = (profile.as_of_date - s.customer_since).days
        return CustomerFeatures(
            customer_id=profile.customer_id,
            as_of_date=profile.as_of_date,
            tenure_months=days // 30,
            active_plan_count=1,
            active_plan_ids=[p.plan_id for p in profile.plans],
            months_observed=6,
            active_months_last_6=0 if s.engagement == EngagementSegment.DORMANT else 6,
            recent_activity_avg=0.0,
            prior_activity_avg=0.0,
            bills_last_12m=min(12, days // 30),
            late_payments_last_6m=0,
            current_bill_state=s.billing.state,
            days_overdue=int(s.billing.verified_facts.get("days_overdue", 0)) or None,
        )


class StubSegmenter:
    def classify(self, features: CustomerFeatures) -> ClassificationResult:
        s = _scenario(features.customer_id)
        segments = [Segment(s.engagement.value)]
        if s.loyalty:
            segments.append(Segment.LOYALTY_CANDIDATE)
        if s.billing.reminder_allowed:
            segments.append(Segment.PAYMENT_REMINDER)
        primary = (
            Segment.PAYMENT_REMINDER
            if Segment.PAYMENT_REMINDER in segments
            else Segment.LOYALTY_CANDIDATE
            if s.loyalty
            else segments[0]
        )
        band = (
            ConfidenceBand.HIGH
            if s.confidence >= 0.75
            else ConfidenceBand.MEDIUM
            if s.confidence >= 0.45
            else ConfidenceBand.LOW
        )
        return ClassificationResult(
            customer_id=features.customer_id,
            as_of_date=features.as_of_date,
            engagement_segment=s.engagement,
            segments=segments,
            primary_segment=primary,
            reason_codes=[ReasonCode(code=c, text=t) for c, t in s.reasons],
            confidence=s.confidence,
            confidence_band=band,
            ruleset_version=f"segments.yaml@{STUB_VERSION}",
        )


class StubClassificationRecorder:
    def record(self, result: ClassificationResult, features: CustomerFeatures) -> str:
        return f"CLS-{uuid.uuid4().hex[:12]}"


class StubCommunicationRecorder:
    """In-memory communication history for mock deliveries (lost on restart)."""

    def __init__(self) -> None:
        self.records: dict[str, list[CommRecord]] = {}

    def record(self, customer_id: str, record: CommRecord) -> None:
        self.records.setdefault(customer_id, []).append(record)


# ---------------------------------------------------------------------------------------
# M2 placeholders
# ---------------------------------------------------------------------------------------
class StubBillingPolicy:
    def evaluate(self, profile: CustomerProfile, features: CustomerFeatures) -> BillingDecision:
        return _scenario(profile.customer_id).billing


class StubOfferEligibility:
    def evaluate(
        self, profile, features, classification, billing, channel="EMAIL"
    ) -> OfferDecision:  # noqa: ANN001
        return _scenario(profile.customer_id).offers


class StubContactPolicy:
    DUPLICATE_WINDOW_DAYS = 7  # placeholder; real value lives in M2's contact.yaml

    def __init__(self, comms: StubCommunicationRecorder) -> None:
        self._comms = comms

    def check(self, profile: CustomerProfile, category: MessageCategory) -> ContactDecision:
        p = profile.preferences
        reasons: list[str] = []
        if p.email_opt_out:
            reasons.append("CONTACT_EMAIL_OPT_OUT")
        if p.preferred_channel == "NONE":
            reasons.append("CONTACT_CHANNEL_NONE")
        if category == MessageCategory.MARKETING and not p.email_marketing_consent:
            reasons.append("CONTACT_NO_MARKETING_CONSENT")
        if category == MessageCategory.SERVICE and not p.email_service_consent:
            reasons.append("CONTACT_NO_SERVICE_CONSENT")
        if profile.account_status != "ACTIVE":
            reasons.append("ACCOUNT_NOT_ACTIVE")
        for rec in self._comms.records.get(profile.customer_id, []):
            gap = abs((profile.as_of_date - rec.sent_at.date()).days)
            if rec.category == category and gap < self.DUPLICATE_WINDOW_DAYS:
                reasons.append("CONTACT_DUPLICATE_RECENT")
                break
        return ContactDecision(allowed=not reasons, category=category, reasons=reasons)


class StubStrategySelector:
    def select(self, classification, billing, offers, contact) -> StrategyDecision:  # noqa: ANN001
        s = _scenario(classification.customer_id)
        if billing.escalate or s.objective == Objective.ESCALATE:
            return StrategyDecision(
                objective=Objective.ESCALATE, rationale_codes=billing.reason_codes or ["ESCALATE"]
            )
        spec = STRATEGY_TABLE[s.objective]
        decision: ContactDecision = contact[spec["category"]]
        if not decision.allowed:
            return StrategyDecision(
                objective=Objective.NO_CONTACT_BY_POLICY,
                category=spec["category"],
                rationale_codes=decision.reasons,
                suppressed=[
                    SuppressedObjective(objective=s.objective, reason_codes=decision.reasons)
                ],
            )
        offer = next(
            (
                e.offer
                for e in offers.eligible
                if e.offer and e.offer.offer_type in spec["offer_types"]
            ),
            None,
        )
        suppressed = []
        if s.loyalty and s.objective in BILLING_OBJECTIVES:
            suppressed.append(
                SuppressedObjective(
                    objective=Objective.LOYALTY_REWARD, reason_codes=["OFFER_BLOCKED_BY_BILLING"]
                )
            )
        return StrategyDecision(
            objective=s.objective,
            category=spec["category"],
            template_id=spec["template_id"],
            template_version=STUB_VERSION,
            tone=spec["tone"],
            allowed_offer=offer,
            required_disclaimer_keys=[
                d for d in spec["disclaimers"] if d != "offer_terms" or offer is not None
            ],
            cta_key=spec["cta"],
            suppressed=suppressed,
            rationale_codes=[f"OBJECTIVE:{s.objective}"] + billing.reason_codes,
        )


CTA_TEXT = {
    "account_cta": "visit your account to explore your plan",
    "reward_cta": "view your reward in your account",
    "plan_cta": "see what is included in your plan in your account",
    "return_cta": "open your account to pick up where you left off",
    "pay_cta": "view and pay your bill in your account",
}
TONE_RULES = {
    "courteous": ["assume an honest oversight", "no blame", "no urgency words"],
    "firm_respectful": ["clear and factual", "no threats, fees or consequences not provided"],
}


class StubLLMInputBuilder:
    def build(self, profile, classification, billing, strategy) -> LLMInput:  # noqa: ANN001
        slots = {"first_name": profile.first_name}
        if profile.plans:
            slots["plan_name"] = profile.plans[0].plan_name
        if strategy.objective in BILLING_OBJECTIVES:
            slots.update(billing.verified_facts)
            slots["support_path"] = SUPPORT_PATH
        if strategy.cta_key:
            slots[strategy.cta_key] = CTA_TEXT[strategy.cta_key]
        offer = None
        if strategy.allowed_offer:
            o = strategy.allowed_offer
            slots.update(
                offer_title=o.title,
                offer_value=o.value_display,
                offer_valid_to=o.valid_to_display,
                offer_terms=o.terms_summary,
            )
            offer = {"offer_id": o.offer_id, "title": o.title}
        return LLMInput(
            first_name=profile.first_name,
            objective=strategy.objective,
            segment_summary=str(classification.primary_segment),
            tone=ToneSpec(name=strategy.tone or "neutral", rules=TONE_RULES.get(strategy.tone, [])),
            allowed_slots=slots,
            offer=offer,
            required_disclaimers=strategy.required_disclaimer_keys,
            forbidden=["threats", "legal action", "late fees", "credit score", "suspension"],
        )


# ---------------------------------------------------------------------------------------
# M3 placeholders
# ---------------------------------------------------------------------------------------
_SIGN_OFF = "\n\nWarm regards,\nCustomer Care Team"
TEMPLATES: dict[Objective, tuple[str, str]] = {
    Objective.APPRECIATION: (
        "Thank you for being with us, {{first_name}}",
        "Hi {{first_name}},\n\nThank you for being a valued customer on your {{plan_name}} "
        "plan. We truly appreciate your continued trust in us.\n\nWhenever you like, you can "
        "{{account_cta}}." + _SIGN_OFF,
    ),
    Objective.LOYALTY_REWARD: (
        "A thank-you reward for you, {{first_name}}",
        "Hi {{first_name}},\n\nThank you for your loyalty. As a thank-you, we would like to "
        "offer you a {{offer_title}}: {{offer_value}}, available until {{offer_valid_to}}.\n\n"
        "You can {{reward_cta}}." + _SIGN_OFF,
    ),
    Objective.REENGAGEMENT: (
        "Make the most of your {{plan_name}}",
        "Hi {{first_name}},\n\nJust checking in. Your {{plan_name}} plan includes benefits "
        "you can use any time, and to help you get started we have {{offer_value}} for you, "
        "available until {{offer_valid_to}}.\n\nYou can {{plan_cta}}." + _SIGN_OFF,
    ),
    Objective.WINBACK: (
        "We would love to have you back, {{first_name}}",
        "Hi {{first_name}},\n\nIt has been a while, and we would love to welcome you back. "
        "Your {{plan_name}} plan is ready whenever you are, and {{offer_value}} is waiting "
        "for you until {{offer_valid_to}}.\n\nYou can {{return_cta}}." + _SIGN_OFF,
    ),
    Objective.BILLING_REMINDER_COURTEOUS: (
        "A friendly reminder about your {{bill_period}} bill",
        "Hi {{first_name}},\n\nThis is a quick reminder that your bill for {{bill_period}} "
        "of {{amount_due}} was due on {{due_date}}. If it slipped your mind, you can "
        "{{pay_cta}}.\n\nIf you have any questions about this bill or believe it is "
        "incorrect, {{support_path}}" + _SIGN_OFF,
    ),
    Objective.BILLING_REMINDER_FOLLOWUP: (
        "Reminder: your {{bill_period}} bill is still open",
        "Hi {{first_name}},\n\nWe wanted to follow up on your bill for {{bill_period}} of "
        "{{amount_due}}, which was due on {{due_date}}. If you have not had a chance yet, "
        "you can {{pay_cta}}.\n\nIf you have any questions about this bill or believe it "
        "is incorrect, {{support_path}}" + _SIGN_OFF,
    ),
    Objective.BILLING_REMINDER_FIRM: (
        "Your {{bill_period}} bill is now overdue",
        "Hi {{first_name}},\n\nYour bill for {{bill_period}} of {{amount_due}} was due on "
        "{{due_date}} and is now {{days_overdue}} days overdue. Please arrange payment: "
        "{{pay_cta}}.\n\nIf you are facing difficulty or believe this bill is incorrect, "
        "we are here to help: {{support_path}}" + _SIGN_OFF,
    ),
}
ADVERSARIAL = (
    "Last chance, {{first_name}}!",
    "Hi {{first_name}},\n\nWe noticed you have not been using your {{plan_name}} much. Get "
    "20% off with code OFF-SPECIAL-20 - but you must pay within 24 hours or face legal "
    "action." + _SIGN_OFF,
)


def disclaimer_text(key: str, slots: dict[str, str]) -> str:
    texts = {
        "unsubscribe": "You are receiving this email because you agreed to hear about offers "
        "from us. To stop these emails, reply with the word unsubscribe.",
        "offer_terms": f"Offer terms: {slots.get('offer_terms', '')} Valid until "
        f"{slots.get('offer_valid_to', '')}.",
        "already_paid": "If you have already paid, please ignore this message.",
        "support_dispute_path": f"Questions or disputes: {SUPPORT_PATH}",
    }
    return texts[key]


class StubMessageGenerator:
    """Template-only generation; C0008 (or LLM_PROVIDER=fake_adversarial) returns unsafe text."""

    def __init__(self, adversarial_provider: bool = False) -> None:
        self._adversarial_provider = adversarial_provider

    def generate(self, llm_input: LLMInput, strategy: StrategyDecision) -> RawDraft:
        is_c0008 = llm_input.first_name == SCENARIOS["C0008"].first_name
        adversarial = self._adversarial_provider or is_c0008
        subject, body = ADVERSARIAL if adversarial else TEMPLATES[strategy.objective]
        return RawDraft(
            subject=subject,
            body=body,
            facts_used=sorted(set(re.findall(r"\{\{\s*(\w+)\s*\}\}", subject + body))),
            offer_id=strategy.allowed_offer.offer_id if strategy.allowed_offer else None,
            disclaimer_keys=list(llm_input.required_disclaimers),
            meta=GenerationMeta(
                model_provider="fake" if adversarial else "template-only",
                model_id="fake-adversarial" if adversarial else "template-only",
                prompt_version="stub" if adversarial else None,
                template_id=strategy.template_id or "none",
                template_version=strategy.template_version or STUB_VERSION,
            ),
        )


_SLOT_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class StubSlotRenderer:
    def render(self, raw: RawDraft, llm_input: LLMInput) -> RenderedDraft:
        slots = llm_input.allowed_slots
        used: dict[str, str] = {}

        def _sub(match: re.Match) -> str:
            name = match.group(1)
            if name in slots:
                used[name] = slots[name]
                return slots[name]
            return match.group(0)  # unknown slot left in place -> guardrail BLOCK

        subject = _SLOT_RE.sub(_sub, raw.subject)
        body = _SLOT_RE.sub(_sub, raw.body)
        if raw.disclaimer_keys:
            body += "\n\n---\n" + "\n".join(disclaimer_text(k, slots) for k in raw.disclaimer_keys)
        return RenderedDraft(
            subject=subject,
            body=body,
            facts_used=used,
            offer_id=raw.offer_id,
            disclaimer_keys=raw.disclaimer_keys,
            meta=raw.meta,
        )


_AMOUNT_RE = re.compile(r"(?:₹|Rs\.?|INR)\s?[\d,]+(?:\.\d+)?", re.IGNORECASE)
_PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s?%")
_RELATIVE_DEADLINE_RE = re.compile(
    r"\b(?:within \d+ (?:hours?|days?)|in \d+ hours?|by tomorrow|by tonight)\b", re.IGNORECASE
)
_OFFER_ID_RE = re.compile(r"\bOFF-[A-Z0-9-]+\b")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<![\w₹.])\+?\d[\d -]{8,}\d\b")
_INTERNAL_RE = re.compile(
    r"\b(?:C\d{4}|ENG_\w+|LOY_\w+|PAY_\w+|BILL_\w+|LOYALTY_CANDIDATE|PAYMENT_REMINDER|"
    r"DECLINING_ACTIVITY|DORMANT)\b"
)
BLOCKED_TERMS = [
    "legal action",
    "lawsuit",
    "blacklist",
    "credit score",
    "final warning",
    "we will disconnect",
    "debt collector",
    "shame",
]
PRESSURE_TERMS = ["urgent", "immediately", "act now", "last chance", "failure to pay"]
OFFER_WORDS = re.compile(r"discount|% off|cashback", re.IGNORECASE)


def _norm(value: str) -> str:
    return (
        re.sub(r"[\s,]", "", value)
        .lower()
        .replace("rs.", "₹")
        .replace("rs", "₹")
        .replace("inr", "₹")
    )


class StubGuardrails:
    """Minimal deterministic checks so BLOCK/WARN paths can be demonstrated end to end."""

    def validate(self, draft: RenderedDraft, ctx: ValidationContext) -> ValidationReport:
        slots = ctx.llm_input.allowed_slots
        text = f"{draft.subject}\n{draft.body}"
        verified_blob = " ".join(
            list(slots.values())
            + [disclaimer_text(k, slots) for k in ctx.llm_input.required_disclaimers]
        )
        findings: list[Finding] = []

        def check(
            check_id: str,
            bad: list[str],
            message: str,
            *,
            mandatory: bool = True,
            severity: Severity = Severity.BLOCK,
        ) -> None:
            if bad:
                findings.append(
                    Finding(
                        check_id=check_id,
                        severity=severity,
                        mandatory=mandatory,
                        message=message,
                        span=bad[0][:80],
                    )
                )
            else:
                findings.append(
                    Finding(
                        check_id=check_id, severity=Severity.PASS, mandatory=mandatory, message="OK"
                    )
                )

        check("UNKNOWN_SLOT", _SLOT_RE.findall(text), "Text contains a slot that was not provided.")
        verified_amounts = {_norm(a) for a in _AMOUNT_RE.findall(verified_blob)}
        check(
            "AMOUNT_GROUNDED",
            [a for a in _AMOUNT_RE.findall(text) if _norm(a) not in verified_amounts],
            "Amount not present in verified facts.",
        )
        verified_pct = {_norm(p) for p in _PERCENT_RE.findall(verified_blob)}
        check(
            "NUMBER_GROUNDED",
            [p for p in _PERCENT_RE.findall(text) if _norm(p) not in verified_pct],
            "Percentage not present in verified facts.",
        )
        check(
            "DATE_GROUNDED",
            _RELATIVE_DEADLINE_RE.findall(text),
            "Deadline or date expression not present in verified facts.",
        )
        allowed = ctx.strategy.allowed_offer
        bad_offer = [o for o in _OFFER_ID_RE.findall(text) if not allowed or o != allowed.offer_id]
        offer_words = OFFER_WORDS.findall(text)
        if offer_words and (not allowed or not OFFER_WORDS.search(allowed.value_display)):
            bad_offer += offer_words
        check(
            "OFFER_ID_VALID", bad_offer, "Offer or offer id that was not approved for this message."
        )
        lowered = text.lower()
        check(
            "BLOCKED_LANGUAGE", [t for t in BLOCKED_TERMS if t in lowered], "Prohibited language."
        )
        check(
            "PII_LEAKAGE",
            _EMAIL_RE.findall(text) + _PHONE_RE.findall(text) + _INTERNAL_RE.findall(text),
            "Personal data or internal code in text.",
        )
        missing = [
            k
            for k in ctx.llm_input.required_disclaimers
            if disclaimer_text(k, slots) not in draft.body
        ]
        check("DISCLAIMER_PRESENT", missing, "Required disclaimer missing.")
        if ctx.strategy.objective in BILLING_OBJECTIVES:
            check(
                "SUPPORT_PATH_PRESENT",
                [] if SUPPORT_PATH in draft.body else ["support path"],
                "Billing reminder must include the support/dispute path.",
            )
            check(
                "FACT_CONTRADICTION",
                ["thank you for your payment"] if "thank you for your payment" in lowered else [],
                "Text contradicts the verified bill state.",
            )
        if ctx.strategy.objective != Objective.BILLING_REMINDER_FIRM:
            check(
                "TONE_KEYWORDS",
                [t for t in PRESSURE_TERMS if t in lowered],
                "Pressure wording in a message that must be courteous.",
                mandatory=False,
                severity=Severity.WARN,
            )
        return ValidationReport(overall=aggregate_severity(findings), findings=findings)


def build_stub_components(adversarial_provider: bool = False):  # noqa: ANN201
    """Return (PipelineComponents, ContactPolicy, CommunicationRecorder) built from stubs."""
    from app.pipeline.orchestrator import PipelineComponents

    comms = StubCommunicationRecorder()
    contact = StubContactPolicy(comms)
    components = PipelineComponents(
        profiles=StubProfileAssembler(),
        features=StubFeatureBuilder(),
        segmenter=StubSegmenter(),
        classifications=StubClassificationRecorder(),
        billing=StubBillingPolicy(),
        offers=StubOfferEligibility(),
        contact=contact,
        strategy=StubStrategySelector(),
        llm_input=StubLLMInputBuilder(),
        generator=StubMessageGenerator(adversarial_provider),
        renderer=StubSlotRenderer(),
        guardrails=StubGuardrails(),
    )
    return components, comms


def demo_customer_list() -> list[dict[str, str]]:
    """For the UI's sample picker while M1's /customers endpoint does not exist."""
    labels = {
        "C0001": "Consistent",
        "C0002": "Loyalty reward",
        "C0003": "Declining activity",
        "C0004": "Dormant",
        "C0005": "Overdue - courteous",
        "C0006": "Overdue - firm",
        "C0007": "Refusal - opted out",
        "C0008": "Unsafe LLM output",
        "C0009": "Loyal + overdue",
        "C0010": "Escalation - disputed",
    }
    return [
        {"customer_id": k, "first_name": SCENARIOS[k].first_name, "hint": v}
        for k, v in labels.items()
    ]
