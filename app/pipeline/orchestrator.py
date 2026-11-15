"""DraftOrchestrator: end-to-end draft pipeline.

Owner: M4 (with M2/M3 review). Follows the sequence in blueprint section 2.4:

profile -> features -> classification -> billing / offers / contact -> strategy
  -> (NO_CONTACT / ESCALATE: stop, no LLM call)
  -> LLM input -> generate -> render slots -> guardrails -> save for human review.

The orchestrator contains no business rules of its own: every decision comes from a component
behind a port. It only sequences calls, persists the result and emits audit events.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session, sessionmaker

from app.audit.logger import AuditLogger
from app.core.clock import utcnow_iso
from app.core.errors import DuplicatePendingDraftError, InvalidStateError
from app.core.logging import get_correlation_id
from app.data.models import DraftRow
from app.pipeline.ports import (
    BillingPolicyPort,
    ClassificationRecorderPort,
    ContactPolicyPort,
    FeatureBuilderPort,
    GuardrailPort,
    LLMInputBuilderPort,
    MessageGeneratorPort,
    OfferEligibilityPort,
    ProfileAssemblerPort,
    SegmenterPort,
    SlotRendererPort,
    StrategySelectorPort,
)
from app.review import repository as repo
from app.review.hashing import compute_content_hash
from app.review.state_machine import REGENERATABLE_STATES, state_after_validation
from app.schemas.api import AnalysisResponse, DraftResponse
from app.schemas.enums import (
    AuditEventType,
    DraftRequestStatus,
    DraftState,
    MessageCategory,
    Objective,
    RejectionReason,
    ReviewerActionType,
    Severity,
)
from app.schemas.validation import ValidationContext


@dataclass(frozen=True)
class PipelineComponents:
    """Everything upstream of review, grouped so the container wires it in one place."""

    profiles: ProfileAssemblerPort
    features: FeatureBuilderPort
    segmenter: SegmenterPort
    classifications: ClassificationRecorderPort
    billing: BillingPolicyPort
    offers: OfferEligibilityPort
    contact: ContactPolicyPort
    strategy: StrategySelectorPort
    llm_input: LLMInputBuilderPort
    generator: MessageGeneratorPort
    renderer: SlotRendererPort
    guardrails: GuardrailPort


class DraftOrchestrator:
    def __init__(
        self,
        components: PipelineComponents,
        session_factory: sessionmaker[Session],
        audit: AuditLogger,
    ) -> None:
        self._c = components
        self._sessions = session_factory
        self._audit = audit

    def analyze(self, customer_id: str, as_of: date) -> AnalysisResponse:
        """Stages 1-8b: everything up to the strategy decision. No LLM, no persistence."""
        c = self._c
        profile = c.profiles.assemble(customer_id, as_of)
        features = c.features.build(profile)
        classification = c.segmenter.classify(features)
        billing = c.billing.evaluate(profile, features)
        offers = c.offers.evaluate(profile, features, classification, billing, "EMAIL")
        contact = {cat: c.contact.check(profile, cat) for cat in MessageCategory}
        strategy = c.strategy.select(classification, billing, offers, contact)
        return AnalysisResponse(
            classification=classification,
            billing=billing,
            offers=offers,
            contact=contact,
            strategy=strategy,
        )

    def create_draft(
        self, customer_id: str, as_of: date, *, regenerate_of: str | None = None
    ) -> DraftResponse:
        c = self._c
        correlation_id = get_correlation_id()
        profile = c.profiles.assemble(customer_id, as_of)
        features = c.features.build(profile)
        classification = c.segmenter.classify(features)
        classification_id = c.classifications.record(classification, features)
        self._audit.log(
            AuditEventType.CLASSIFIED,
            customer_ref=customer_id,
            payload={
                "classification_id": classification_id,
                "segments": [str(s) for s in classification.segments],
                "primary_segment": str(classification.primary_segment),
                "confidence": classification.confidence,
                "confidence_band": str(classification.confidence_band),
                "reason_codes": [r.code for r in classification.reason_codes],
                "ruleset_version": classification.ruleset_version,
                "as_of_date": as_of.isoformat(),
            },
        )

        billing = c.billing.evaluate(profile, features)
        offers = c.offers.evaluate(profile, features, classification, billing, "EMAIL")
        contact = {cat: c.contact.check(profile, cat) for cat in MessageCategory}
        strategy = c.strategy.select(classification, billing, offers, contact)
        analysis = AnalysisResponse(
            classification=classification,
            billing=billing,
            offers=offers,
            contact=contact,
            strategy=strategy,
        )
        self._audit.log(
            AuditEventType.POLICY_DECIDED,
            customer_ref=customer_id,
            payload={
                "objective": str(strategy.objective),
                "category": str(strategy.category) if strategy.category else None,
                "template_id": strategy.template_id,
                "offer_id": strategy.allowed_offer.offer_id if strategy.allowed_offer else None,
                "bill_state": str(billing.state),
                "reminder_stage": billing.stage,
                "offers_eligible": [o.offer_id for o in offers.eligible],
                "offers_rejected": {o.offer_id: o.failed_checks for o in offers.rejected},
                "contact": {str(k): v.allowed for k, v in contact.items()},
                "rationale_codes": strategy.rationale_codes,
            },
        )

        # Pre-generation gate: never ask the LLM to write a message that may not be sent.
        if strategy.objective in (Objective.NO_CONTACT, Objective.NO_CONTACT_BY_POLICY):
            reasons = strategy.rationale_codes or [str(strategy.objective)]
            self._audit.log(
                AuditEventType.REFUSED, customer_ref=customer_id, payload={"reasons": reasons}
            )
            return DraftResponse(
                status=DraftRequestStatus.REFUSED,
                correlation_id=correlation_id,
                refusal_reasons=reasons,
                analysis=analysis,
            )
        if strategy.objective == Objective.ESCALATE:
            reasons = strategy.rationale_codes or [str(strategy.objective)]
            self._audit.log(
                AuditEventType.ESCALATED, customer_ref=customer_id, payload={"reasons": reasons}
            )
            return DraftResponse(
                status=DraftRequestStatus.ESCALATED,
                correlation_id=correlation_id,
                refusal_reasons=reasons,
                analysis=analysis,
            )

        self._check_no_open_draft(customer_id, regenerate_of)

        llm_input = c.llm_input.build(profile, classification, billing, strategy)
        raw = c.generator.generate(llm_input, strategy)
        rendered = c.renderer.render(raw, llm_input)
        context = ValidationContext(llm_input=llm_input, strategy=strategy)
        report = c.guardrails.validate(rendered, context)
        report = report.model_copy(update={"validation_run": 1})
        state = state_after_validation(report.overall)

        draft_id = str(uuid.uuid4())
        now = utcnow_iso()
        meta = rendered.meta
        row = DraftRow(
            draft_id=draft_id,
            customer_id=customer_id,
            classification_id=classification_id,
            objective=str(strategy.objective),
            template_id=meta.template_id,
            template_version=meta.template_version,
            prompt_version=meta.prompt_version,
            model_provider=meta.model_provider,
            model_id=meta.model_id,
            fallback_used=int(meta.fallback_used),
            offer_id=rendered.offer_id,
            bill_id=billing.bill_id if billing.reminder_allowed else None,
            reminder_stage=billing.stage if billing.reminder_allowed else None,
            subject=rendered.subject,
            body=rendered.body,
            facts_used=rendered.facts_used,
            content_hash=compute_content_hash(rendered.subject, rendered.body),
            validation_status=str(report.overall),
            validation_run=1,
            state=str(state),
            policy_decisions={
                **analysis.model_dump(mode="json"),
                "disclaimer_keys": rendered.disclaimer_keys,
                "validation_context": context.model_dump(mode="json"),
            },
            regenerated_from=regenerate_of,
            llm_latency_ms=meta.llm_latency_ms,
            prompt_tokens=meta.prompt_tokens,
            completion_tokens=meta.completion_tokens,
            created_at=now,
            updated_at=now,
        )
        with self._sessions.begin() as session:
            if regenerate_of:
                self._supersede(session, regenerate_of, customer_id)
            session.add(row)
            session.flush()
            repo.add_findings(session, draft_id, report)
            view = repo.build_view(session, row)

        if regenerate_of:
            self._audit.log(
                AuditEventType.REJECTED,
                customer_ref=customer_id,
                draft_id=regenerate_of,
                payload={"reason": str(RejectionReason.OTHER), "superseded_by": draft_id},
            )
        if meta.fallback_used:
            self._audit.log(
                AuditEventType.LLM_FALLBACK,
                customer_ref=customer_id,
                draft_id=draft_id,
                payload={"reason": meta.fallback_reason, "model_id": meta.model_id},
            )
        self._audit.log(
            AuditEventType.DRAFT_GENERATED,
            customer_ref=customer_id,
            draft_id=draft_id,
            payload={
                "objective": str(strategy.objective),
                "model_provider": meta.model_provider,
                "model_id": meta.model_id,
                "prompt_version": meta.prompt_version,
                "template": f"{meta.template_id}@{meta.template_version}",
                "facts_keys": sorted(rendered.facts_used),
                "offer_id": rendered.offer_id,
                "content_hash": row.content_hash,
                "regenerated_from": regenerate_of,
                "llm_latency_ms": meta.llm_latency_ms,
            },
        )
        self._audit.log(
            AuditEventType.VALIDATED,
            customer_ref=customer_id,
            draft_id=draft_id,
            payload={
                "overall": str(report.overall),
                "validation_run": 1,
                "failed_checks": [
                    f.check_id for f in report.findings if f.severity != Severity.PASS
                ],
            },
        )
        return DraftResponse(
            status=DraftRequestStatus.CREATED,
            correlation_id=correlation_id,
            draft=view,
            validation=report,
            analysis=analysis,
        )

    # ---- helpers -------------------------------------------------------------------------
    def _check_no_open_draft(self, customer_id: str, regenerate_of: str | None) -> None:
        with self._sessions() as session:
            open_ids = [d.draft_id for d in repo.open_drafts_for(session, customer_id)]
            if regenerate_of:
                original = repo.get_draft(session, regenerate_of)
                if original.customer_id != customer_id:
                    raise InvalidStateError("regenerate_of belongs to a different customer.")
                if DraftState(original.state) not in REGENERATABLE_STATES:
                    raise InvalidStateError(
                        f"Draft in state {original.state} cannot be regenerated.",
                        details={"state": original.state},
                    )
        others = [d for d in open_ids if d != regenerate_of]
        if others:
            raise DuplicatePendingDraftError(
                "This customer already has an open draft; finish or reject it first.",
                details={"open_draft_ids": others},
            )

    @staticmethod
    def _supersede(session: Session, draft_id: str, customer_id: str) -> None:
        """Close the draft being regenerated so only one open draft exists."""
        original = repo.get_draft(session, draft_id)
        original.state = str(DraftState.REJECTED)
        original.updated_at = utcnow_iso()
        repo.add_action(
            session,
            draft_id=draft_id,
            reviewer_id="system",
            action=ReviewerActionType.REJECT,
            content_hash=original.content_hash,
            comment="Superseded by regeneration.",
            rejection_reason=RejectionReason.OTHER,
        )
