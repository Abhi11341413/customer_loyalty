"""Persistence for drafts, validation findings, reviewer actions and deliveries (T14-T17).

Owner: M4. Functions take an open Session so callers control the transaction boundary.
"""

from __future__ import annotations

import uuid

from sqlalchemy import literal_column, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow_iso
from app.core.errors import DraftNotFoundError
from app.data.models import DeliveryRow, DraftRow, ReviewerActionRow, ValidationFindingRow
from app.review.state_machine import OPEN_STATES, allowed_actions
from app.schemas.enums import (
    DeliveryStatus,
    DraftState,
    Objective,
    RejectionReason,
    ReviewerActionType,
    Severity,
)
from app.schemas.review import (
    DeliveryResult,
    DraftSummary,
    DraftView,
    ModelInfo,
    ReviewerAction,
    Rubric,
)
from app.schemas.validation import Finding, ValidationReport


def get_draft(session: Session, draft_id: str) -> DraftRow:
    row = session.get(DraftRow, draft_id)
    if row is None:
        raise DraftNotFoundError("Draft not found.", details={"draft_id": draft_id})
    return row


def add_findings(session: Session, draft_id: str, report: ValidationReport) -> None:
    for finding in report.findings:
        session.add(
            ValidationFindingRow(
                finding_id=uuid.uuid4().hex,
                draft_id=draft_id,
                validation_run=report.validation_run,
                check_id=finding.check_id,
                severity=str(finding.severity),
                mandatory=int(finding.mandatory),
                message=finding.message,
                span=finding.span,
            )
        )


def latest_report(session: Session, row: DraftRow) -> ValidationReport:
    stmt = (
        select(ValidationFindingRow)
        .where(ValidationFindingRow.draft_id == row.draft_id)
        .where(ValidationFindingRow.validation_run == row.validation_run)
        .order_by(literal_column("validation_findings.rowid"))
    )
    findings = [
        Finding(
            check_id=f.check_id,
            severity=Severity(f.severity),
            mandatory=bool(f.mandatory),
            message=f.message,
            span=f.span,
        )
        for f in session.scalars(stmt)
    ]
    return ValidationReport(
        overall=Severity(row.validation_status),
        findings=findings,
        validation_run=row.validation_run,
    )


def add_action(
    session: Session,
    *,
    draft_id: str,
    reviewer_id: str,
    action: ReviewerActionType,
    content_hash: str,
    comment: str | None = None,
    rubric: Rubric | None = None,
    rejection_reason: RejectionReason | None = None,
) -> ReviewerActionRow:
    row = ReviewerActionRow(
        action_id=uuid.uuid4().hex,
        draft_id=draft_id,
        reviewer_id=reviewer_id,
        action=str(action),
        content_hash=content_hash,
        comment=comment,
        rubric=rubric.model_dump() if rubric else None,
        rejection_reason=str(rejection_reason) if rejection_reason else None,
        created_at=utcnow_iso(),
    )
    session.add(row)
    session.flush()
    return row


def list_actions(session: Session, draft_id: str) -> list[ReviewerActionRow]:
    stmt = (
        select(ReviewerActionRow)
        .where(ReviewerActionRow.draft_id == draft_id)
        .order_by(literal_column("reviewer_actions.rowid"))
    )
    return list(session.scalars(stmt))


def latest_action(
    session: Session, draft_id: str, action: ReviewerActionType
) -> ReviewerActionRow | None:
    stmt = (
        select(ReviewerActionRow)
        .where(ReviewerActionRow.draft_id == draft_id)
        .where(ReviewerActionRow.action == str(action))
        .order_by(literal_column("reviewer_actions.rowid").desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def get_delivery(session: Session, draft_id: str) -> DeliveryRow | None:
    return session.scalars(select(DeliveryRow).where(DeliveryRow.draft_id == draft_id)).first()


def upsert_delivery(
    session: Session,
    *,
    draft_id: str,
    status: DeliveryStatus,
    block_reason: str | None = None,
    outbox_path: str | None = None,
) -> DeliveryRow:
    """One delivery row per draft; a BLOCKED attempt is overwritten by a later outcome."""
    row = get_delivery(session, draft_id)
    if row is None:
        row = DeliveryRow(delivery_id=uuid.uuid4().hex, draft_id=draft_id)
        session.add(row)
    row.status = str(status)
    row.block_reason = block_reason
    row.outbox_path = outbox_path
    row.delivered_at = utcnow_iso()
    session.flush()
    return row


def open_drafts_for(session: Session, customer_id: str) -> list[DraftRow]:
    stmt = (
        select(DraftRow)
        .where(DraftRow.customer_id == customer_id)
        .where(DraftRow.state.in_([str(s) for s in OPEN_STATES]))
    )
    return list(session.scalars(stmt))


def _delivery_result(row: DeliveryRow) -> DeliveryResult:
    return DeliveryResult(
        draft_id=row.draft_id,
        status=DeliveryStatus(row.status),
        block_reason=row.block_reason,
        outbox_path=row.outbox_path,
        delivered_at=row.delivered_at,
    )


def _action_view(row: ReviewerActionRow) -> ReviewerAction:
    return ReviewerAction(
        action_id=row.action_id,
        draft_id=row.draft_id,
        reviewer_id=row.reviewer_id,
        action=ReviewerActionType(row.action),
        content_hash=row.content_hash,
        comment=row.comment,
        rubric=Rubric.model_validate(row.rubric) if row.rubric else None,
        rejection_reason=RejectionReason(row.rejection_reason) if row.rejection_reason else None,
        created_at=row.created_at,
    )


def build_view(session: Session, row: DraftRow) -> DraftView:
    report = latest_report(session, row)
    delivery = get_delivery(session, row.draft_id)
    decisions = dict(row.policy_decisions or {})
    decisions.pop("validation_context", None)  # internal; holds the LLM input
    state = DraftState(row.state)
    return DraftView(
        draft_id=row.draft_id,
        customer_id=row.customer_id,
        state=state,
        objective=Objective(row.objective),
        subject=row.subject,
        body=row.body,
        offer_id=row.offer_id,
        bill_id=row.bill_id,
        reminder_stage=row.reminder_stage,
        facts_used=row.facts_used or {},
        model=ModelInfo(
            provider=row.model_provider,
            model_id=row.model_id,
            prompt_version=row.prompt_version,
            template=f"{row.template_id}@{row.template_version}",
            fallback_used=bool(row.fallback_used),
        ),
        content_hash=row.content_hash,
        validation=report,
        policy_decisions=decisions,
        reviewer_actions=[_action_view(a) for a in list_actions(session, row.draft_id)],
        delivery=_delivery_result(delivery) if delivery else None,
        allowed_actions=allowed_actions(state, report.overall),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_summaries(
    session: Session,
    *,
    customer_id: str | None = None,
    state: DraftState | None = None,
    limit: int = 100,
) -> list[DraftSummary]:
    stmt = select(DraftRow)
    if customer_id:
        stmt = stmt.where(DraftRow.customer_id == customer_id)
    if state:
        stmt = stmt.where(DraftRow.state == str(state))
    stmt = stmt.order_by(DraftRow.created_at.desc()).limit(max(1, min(limit, 200)))
    summaries: list[DraftSummary] = []
    for row in session.scalars(stmt):
        actions = list_actions(session, row.draft_id)
        delivery = get_delivery(session, row.draft_id)
        summaries.append(
            DraftSummary(
                draft_id=row.draft_id,
                customer_id=row.customer_id,
                objective=Objective(row.objective),
                model_id=row.model_id,
                validation_status=Severity(row.validation_status),
                state=DraftState(row.state),
                last_reviewer_id=actions[-1].reviewer_id if actions else None,
                delivery_status=DeliveryStatus(delivery.status) if delivery else None,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    return summaries
