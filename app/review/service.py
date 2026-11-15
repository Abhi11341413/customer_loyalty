"""ReviewService: state machine, edit -> re-validate, approval bound to content hash.

Owner: M4. Implements FR-08.

Rules enforced here (never in the UI):
- Every edit is re-validated with the same verified facts the draft was generated from.
- Approval requires: state PENDING_REVIEW, the caller's hash equals the current content hash,
  validation PASS/WARN, and WARN acknowledged.
- Any edit after approval invalidates it (the draft returns to review).
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.audit.logger import AuditLogger
from app.core.clock import utcnow_iso
from app.core.errors import (
    HashMismatchError,
    InvalidStateError,
    ValidationBlockedError,
    WarningsNotAcknowledgedError,
)
from app.data.models import DraftRow
from app.pipeline.ports import GuardrailPort
from app.review import repository as repo
from app.review.hashing import compute_content_hash
from app.review.state_machine import (
    APPROVABLE_SEVERITIES,
    EDITABLE_STATES,
    REVALIDATABLE_STATES,
    ensure_transition,
    state_after_validation,
)
from app.schemas.enums import (
    AuditEventType,
    DraftState,
    RejectionReason,
    ReviewerActionType,
    Severity,
)
from app.schemas.generation import GenerationMeta, RenderedDraft
from app.schemas.review import DraftSummary, DraftView, Rubric
from app.schemas.validation import ValidationContext, ValidationReport


def rendered_from_row(row: DraftRow) -> RenderedDraft:
    """Rebuild the RenderedDraft for the draft's *current* text (used for re-validation)."""
    return RenderedDraft(
        subject=row.subject,
        body=row.body,
        facts_used=row.facts_used or {},
        offer_id=row.offer_id,
        disclaimer_keys=list((row.policy_decisions or {}).get("disclaimer_keys", [])),
        meta=GenerationMeta(
            model_provider=row.model_provider,
            model_id=row.model_id,
            prompt_version=row.prompt_version,
            template_id=row.template_id,
            template_version=row.template_version,
            fallback_used=bool(row.fallback_used),
        ),
    )


def validation_context_from_row(row: DraftRow) -> ValidationContext:
    stored = (row.policy_decisions or {}).get("validation_context")
    if not stored:
        raise InvalidStateError("Draft has no stored validation context; regenerate it.")
    return ValidationContext.model_validate(stored)


class ReviewService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        guardrails: GuardrailPort,
        audit: AuditLogger,
    ) -> None:
        self._sessions = session_factory
        self._guardrails = guardrails
        self._audit = audit

    # ---- queries -------------------------------------------------------------------------
    def get(self, draft_id: str) -> DraftView:
        with self._sessions() as session:
            return repo.build_view(session, repo.get_draft(session, draft_id))

    def list(
        self, *, customer_id: str | None = None, state: DraftState | None = None, limit: int = 100
    ) -> list[DraftSummary]:
        with self._sessions() as session:
            return repo.list_summaries(session, customer_id=customer_id, state=state, limit=limit)

    # ---- commands ------------------------------------------------------------------------
    def _run_validation(self, session: Session, row: DraftRow) -> ValidationReport:
        """Validate the row's current text, persist findings as a new run, update status."""
        report = self._guardrails.validate(rendered_from_row(row), validation_context_from_row(row))
        report = report.model_copy(update={"validation_run": row.validation_run + 1})
        row.validation_run = report.validation_run
        row.validation_status = str(report.overall)
        repo.add_findings(session, row.draft_id, report)
        return report

    def edit(self, draft_id: str, *, reviewer_id: str, subject: str, body: str) -> DraftView:
        with self._sessions.begin() as session:
            row = repo.get_draft(session, draft_id)
            current = DraftState(row.state)
            if current not in EDITABLE_STATES:
                raise InvalidStateError(
                    f"Draft in state {current} cannot be edited.", details={"state": str(current)}
                )
            was_approved = current == DraftState.APPROVED
            row.subject, row.body = subject, body
            row.content_hash = compute_content_hash(subject, body)
            report = self._run_validation(session, row)
            target = state_after_validation(report.overall)
            ensure_transition(current, target)
            row.state = str(target)
            row.updated_at = utcnow_iso()
            repo.add_action(
                session,
                draft_id=draft_id,
                reviewer_id=reviewer_id,
                action=ReviewerActionType.EDIT,
                content_hash=row.content_hash,
            )
            customer_id = row.customer_id
            view = repo.build_view(session, row)
        self._audit.log(
            AuditEventType.EDITED,
            actor=reviewer_id,
            customer_ref=customer_id,
            draft_id=draft_id,
            payload={"approval_invalidated": was_approved, "new_state": str(target)},
        )
        self._log_validated(customer_id, draft_id, report)
        return view

    def revalidate(self, draft_id: str) -> ValidationReport:
        with self._sessions.begin() as session:
            row = repo.get_draft(session, draft_id)
            current = DraftState(row.state)
            if current not in REVALIDATABLE_STATES:
                raise InvalidStateError(
                    f"Draft in state {current} cannot be re-validated.",
                    details={"state": str(current)},
                )
            report = self._run_validation(session, row)
            # An approved draft keeps its approval; the delivery gate re-checks validation.
            if current != DraftState.APPROVED:
                target = state_after_validation(report.overall)
                ensure_transition(current, target)
                row.state = str(target)
            row.updated_at = utcnow_iso()
            customer_id = row.customer_id
        self._log_validated(customer_id, draft_id, report)
        return report

    def approve(
        self,
        draft_id: str,
        *,
        reviewer_id: str,
        content_hash: str,
        comment: str | None = None,
        rubric: Rubric | None = None,
        acknowledge_warnings: bool = False,
    ) -> DraftView:
        with self._sessions.begin() as session:
            row = repo.get_draft(session, draft_id)
            current = DraftState(row.state)
            severity = Severity(row.validation_status)
            if current in (DraftState.BLOCKED, DraftState.ESCALATED) or (
                severity not in APPROVABLE_SEVERITIES
            ):
                raise ValidationBlockedError(
                    "Draft failed mandatory checks or needs escalation; it cannot be approved.",
                    details={"state": str(current), "validation": str(severity)},
                )
            if current != DraftState.PENDING_REVIEW:
                raise InvalidStateError(
                    f"Draft in state {current} cannot be approved.", details={"state": str(current)}
                )
            if content_hash != row.content_hash:
                raise HashMismatchError(
                    "The draft changed since you reviewed it; reload and review again."
                )
            if severity == Severity.WARN and not acknowledge_warnings:
                raise WarningsNotAcknowledgedError("Review and acknowledge the warnings first.")
            ensure_transition(current, DraftState.APPROVED)
            row.state = str(DraftState.APPROVED)
            row.updated_at = utcnow_iso()
            repo.add_action(
                session,
                draft_id=draft_id,
                reviewer_id=reviewer_id,
                action=ReviewerActionType.APPROVE,
                content_hash=row.content_hash,
                comment=comment,
                rubric=rubric,
            )
            customer_id = row.customer_id
            view = repo.build_view(session, row)
        self._audit.log(
            AuditEventType.APPROVED,
            actor=reviewer_id,
            customer_ref=customer_id,
            draft_id=draft_id,
            payload={
                "content_hash": content_hash,
                "validation": str(severity),
                "warnings_acknowledged": acknowledge_warnings,
            },
        )
        return view

    def reject(
        self,
        draft_id: str,
        *,
        reviewer_id: str,
        reason: RejectionReason,
        comment: str | None = None,
        rubric: Rubric | None = None,
    ) -> DraftView:
        with self._sessions.begin() as session:
            row = repo.get_draft(session, draft_id)
            ensure_transition(DraftState(row.state), DraftState.REJECTED)
            row.state = str(DraftState.REJECTED)
            row.updated_at = utcnow_iso()
            repo.add_action(
                session,
                draft_id=draft_id,
                reviewer_id=reviewer_id,
                action=ReviewerActionType.REJECT,
                content_hash=row.content_hash,
                comment=comment,
                rubric=rubric,
                rejection_reason=reason,
            )
            customer_id = row.customer_id
            view = repo.build_view(session, row)
        self._audit.log(
            AuditEventType.REJECTED,
            actor=reviewer_id,
            customer_ref=customer_id,
            draft_id=draft_id,
            payload={"reason": str(reason)},
        )
        return view

    def _log_validated(self, customer_id: str, draft_id: str, report: ValidationReport) -> None:
        self._audit.log(
            AuditEventType.VALIDATED,
            customer_ref=customer_id,
            draft_id=draft_id,
            payload={
                "overall": str(report.overall),
                "validation_run": report.validation_run,
                "failed_checks": [
                    f.check_id for f in report.findings if f.severity != Severity.PASS
                ],
            },
        )
