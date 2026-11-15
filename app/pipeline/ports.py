"""Interfaces the orchestrator, review service and delivery gate depend on (DIP, section 3.5).

Owner: M4. Each Protocol is implemented by the owning member's component and wired in
`app/core/container.py`. Method shapes follow the sequence in blueprint section 2.4; owners,
tell M4 if a signature does not fit your component.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from app.schemas.classification import ClassificationResult
from app.schemas.customer import CommRecord, CustomerFeatures, CustomerProfile
from app.schemas.enums import MessageCategory
from app.schemas.generation import LLMInput, RawDraft, RenderedDraft
from app.schemas.policy import (
    BillingDecision,
    ContactDecision,
    OfferDecision,
    StrategyDecision,
)
from app.schemas.validation import ValidationContext, ValidationReport


class ProfileAssemblerPort(Protocol):  # M1
    def assemble(self, customer_id: str, as_of: date) -> CustomerProfile:
        """Raise app.core.errors.CustomerNotFoundError for unknown ids."""
        ...


class FeatureBuilderPort(Protocol):  # M1
    def build(self, profile: CustomerProfile) -> CustomerFeatures: ...


class SegmenterPort(Protocol):  # M1
    def classify(self, features: CustomerFeatures) -> ClassificationResult: ...


class ClassificationRecorderPort(Protocol):  # M1 (persists to classification_results)
    def record(self, result: ClassificationResult, features: CustomerFeatures) -> str:
        """Persist the result and return its classification_id."""
        ...


class BillingPolicyPort(Protocol):  # M2
    def evaluate(self, profile: CustomerProfile, features: CustomerFeatures) -> BillingDecision: ...


class OfferEligibilityPort(Protocol):  # M2
    def evaluate(
        self,
        profile: CustomerProfile,
        features: CustomerFeatures,
        classification: ClassificationResult,
        billing: BillingDecision,
        channel: str = "EMAIL",
    ) -> OfferDecision: ...


class ContactPolicyPort(Protocol):  # M2 (also reused by DeliveryGate, decision D5)
    def check(self, profile: CustomerProfile, category: MessageCategory) -> ContactDecision: ...


class StrategySelectorPort(Protocol):  # M2
    def select(
        self,
        classification: ClassificationResult,
        billing: BillingDecision,
        offers: OfferDecision,
        contact: dict[MessageCategory, ContactDecision],
    ) -> StrategyDecision: ...


class LLMInputBuilderPort(Protocol):  # M2 (app/policy/llm_input.py)
    def build(
        self,
        profile: CustomerProfile,
        classification: ClassificationResult,
        billing: BillingDecision,
        strategy: StrategyDecision,
    ) -> LLMInput: ...


class MessageGeneratorPort(Protocol):  # M3 (includes the fallback chain)
    def generate(self, llm_input: LLMInput, strategy: StrategyDecision) -> RawDraft: ...


class SlotRendererPort(Protocol):  # M3
    def render(self, raw: RawDraft, llm_input: LLMInput) -> RenderedDraft: ...


class GuardrailPort(Protocol):  # M3
    def validate(self, draft: RenderedDraft, ctx: ValidationContext) -> ValidationReport: ...


class CommunicationRecorderPort(Protocol):  # M1 (writes communication_history)
    def record(self, customer_id: str, record: CommRecord) -> None:
        """Store metadata of a mock delivery so frequency/duplicate checks see it."""
        ...
