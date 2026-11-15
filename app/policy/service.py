"""Policy components with the method shapes M4's orchestrator expects.

Owner: M2. These are thin adapters: they take M1's ``CustomerProfile`` /
``CustomerFeatures`` / ``ClassificationResult`` and call the pure functions in
``billing.py``, ``offers.py``, ``contact.py``, ``strategy.py`` and ``llm_input.py``.

They implement M4's ports (``app/pipeline/ports.py`` in PR #3)::

    BillingPolicyPort     -> BillingPolicyEngine.evaluate(profile, features)
    OfferEligibilityPort  -> OfferEligibilityEngine.evaluate(profile, features, classification,
                                                             billing, channel)
    ContactPolicyPort     -> ContactPolicyGate.check(profile, category)
    StrategySelectorPort  -> StrategySelector.select(classification, billing, offers, contact)
    LLMInputBuilderPort   -> LLMInputBuilder.build(profile, classification, billing, strategy)

``PolicyService`` bundles them for the policy API and the integration test.

Duplicate-outreach note: the orchestrator asks the contact gate once per category, before
an objective is chosen, so the "same objective within 7 days" rule cannot run there. It is
still covered: marketing emails have a stricter 14-day gap, and billing reminders have a
per-bill 7-day gap in the billing engine.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.data.repositories.offer_repo import OfferReader, SqlOfferReader
from app.policy.billing import decide_billing
from app.policy.config import (
    BillingConfig,
    ContactConfig,
    StrategyConfig,
    load_billing_config,
    load_contact_config,
    load_strategy_config,
)
from app.policy.contact import check_contact
from app.policy.llm_input import build_llm_input
from app.policy.offers import decide_offers
from app.policy.strategy import apply_contact, select_strategy
from app.schemas.classification import ClassificationResult
from app.schemas.customer import CustomerFeatures, CustomerProfile
from app.schemas.enums import MessageCategory
from app.schemas.generation import LLMInput
from app.schemas.policy import (
    BillingDecision,
    ContactDecision,
    OfferCustomerContext,
    OfferDecision,
    StrategyDecision,
)

CONTACT_DECISION_MISSING = "CONTACT_DECISION_MISSING"


class BillingPolicyEngine:
    def __init__(self, cfg: BillingConfig | None = None) -> None:
        self.cfg = cfg or load_billing_config()

    def evaluate(
        self, profile: CustomerProfile, features: CustomerFeatures | None = None
    ) -> BillingDecision:
        return decide_billing(
            profile.bills, profile.payments, profile.communications, self.cfg, profile.as_of_date
        )


class OfferEligibilityEngine:
    def __init__(self, reader: OfferReader, contact_cfg: ContactConfig | None = None) -> None:
        self.reader = reader
        self.duplicate_window_days = (
            contact_cfg or load_contact_config()
        ).duplicate_window_days.same_offer

    def evaluate(
        self,
        profile: CustomerProfile,
        features: CustomerFeatures,
        classification: ClassificationResult,
        billing: BillingDecision,
        channel: str = "EMAIL",
        candidate_offer_ids: list[str] | None = None,
    ) -> OfferDecision:
        customer = OfferCustomerContext(
            customer_id=profile.customer_id,
            segments=frozenset(classification.segments),
            tenure_months=features.tenure_months,
            active_plan_ids=frozenset(features.active_plan_ids),
            account_status=profile.account_status,
            bill_state=billing.state,  # the policy engine's state is authoritative (§6.2)
        )
        return decide_offers(
            customer,
            self.reader.offers(),
            self.reader.campaigns(),
            redemptions=self.reader.redemptions_for(profile.customer_id, profile.as_of_date),
            history=profile.communications,
            as_of=profile.as_of_date,
            channel=channel,
            candidate_offer_ids=candidate_offer_ids,
            duplicate_window_days=self.duplicate_window_days,
        )


class ContactPolicyGate:
    """Also reused by M4's DeliveryGate at send time (D5)."""

    def __init__(self, cfg: ContactConfig | None = None) -> None:
        self.cfg = cfg or load_contact_config()

    def check(
        self,
        profile: CustomerProfile,
        category: MessageCategory,
        objective: str | None = None,
        as_of: date | None = None,
    ) -> ContactDecision:
        return check_contact(
            profile.contact_preferences,
            profile.account_status,
            profile.communications,
            category,
            objective,
            self.cfg,
            as_of or profile.as_of_date,
        )

    def check_all(self, profile: CustomerProfile) -> dict[MessageCategory, ContactDecision]:
        return {cat: self.check(profile, cat) for cat in MessageCategory}


class StrategySelector:
    def __init__(self, cfg: StrategyConfig | None = None) -> None:
        self.cfg = cfg or load_strategy_config()

    def select(
        self,
        classification: ClassificationResult,
        billing: BillingDecision,
        offers: OfferDecision,
        contact: Mapping[MessageCategory, ContactDecision],
    ) -> StrategyDecision:
        plan = select_strategy(classification.segments, billing, offers, self.cfg)
        if plan.category is None:
            return plan  # ESCALATE / NO_CONTACT: nothing to check
        decision = contact.get(plan.category) or ContactDecision(
            allowed=False, category=plan.category, reasons=[CONTACT_DECISION_MISSING]
        )
        return apply_contact(plan, decision)


class LLMInputBuilder:
    def __init__(
        self,
        cfg: StrategyConfig | None = None,
        tone_rules: Mapping[str, list[str]] | None = None,
    ) -> None:
        self.cfg = cfg or load_strategy_config()
        #: tone name -> rules; M3 owns config/policies/tone.yaml and can inject it here.
        self.tone_rules = dict(tone_rules or {})

    def build(
        self,
        profile: CustomerProfile,
        classification: ClassificationResult,
        billing: BillingDecision,
        strategy: StrategyDecision,
    ) -> LLMInput:
        active = [p for p in profile.plans if p.status == "ACTIVE"]
        return build_llm_input(
            strategy,
            first_name=profile.first_name,
            billing=billing,
            cfg=self.cfg,
            plan_name=active[0].plan_name if active else None,
            tone_rules=self.tone_rules.get(strategy.tone or "", []),
        )


@dataclass(frozen=True)
class PolicyAnalysis:
    billing: BillingDecision
    offers: OfferDecision
    contact: dict[MessageCategory, ContactDecision]
    strategy: StrategyDecision


class PolicyService:
    """All M2 components, wired for one DB session."""

    def __init__(
        self,
        billing: BillingPolicyEngine,
        offers: OfferEligibilityEngine,
        contact: ContactPolicyGate,
        strategy: StrategySelector,
        llm_input: LLMInputBuilder,
    ) -> None:
        self.billing, self.offers, self.contact = billing, offers, contact
        self.strategy, self.llm_input = strategy, llm_input

    @classmethod
    def from_session(cls, session: Session) -> "PolicyService":
        return cls(
            BillingPolicyEngine(),
            OfferEligibilityEngine(SqlOfferReader(session)),
            ContactPolicyGate(),
            StrategySelector(),
            LLMInputBuilder(),
        )

    def analyze(
        self,
        profile: CustomerProfile,
        features: CustomerFeatures,
        classification: ClassificationResult,
    ) -> PolicyAnalysis:
        billing = self.billing.evaluate(profile, features)
        offers = self.offers.evaluate(profile, features, classification, billing)
        contact = self.contact.check_all(profile)
        strategy = self.strategy.select(classification, billing, offers, contact)
        return PolicyAnalysis(billing=billing, offers=offers, contact=contact, strategy=strategy)
