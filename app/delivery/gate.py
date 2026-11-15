"""DeliveryGate: final re-check before mock send.

Owner: M4. Implements the "block sending" half of FR-10.

Nothing is sent unless ALL of these hold at the moment of delivery:
1. the draft is APPROVED;
2. the latest approval was given for exactly the current text (content hash), and the stored
   hash still matches the text (tamper check);
3. the guardrails, re-run now, do not return BLOCK or ESCALATE;
4. the contact policy (consent, opt-out, frequency, duplicates) still allows contact;
5. the recipient is on the synthetic `example.test` domain.
There is no flag that skips any of these.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session, sessionmaker

from app.audit.logger import AuditLogger
from app.core.clock import utcnow, utcnow_iso
from app.core.errors import DeliveryBlockedError, InvalidStateError, NotApprovedError
from app.delivery.mock_email import ALLOWED_RECIPIENT_DOMAIN, MockEmailService
from app.pipeline.ports import (
    CommunicationRecorderPort,
    ContactPolicyPort,
    GuardrailPort,
    ProfileAssemblerPort,
)
from app.review import repository as repo
from app.review.hashing import compute_content_hash
from app.review.service import rendered_from_row, validation_context_from_row
from app.schemas.customer import CommRecord
from app.schemas.enums import (
    AuditEventType,
    DeliveryStatus,
    DraftState,
    MessageCategory,
    ReviewerActionType,
    Severity,
)
from app.schemas.review import DeliveryResult
from app.schemas.validation import ValidationReport

NOT_APPROVED = "NOT_APPROVED"


class DeliveryGate:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        guardrails: GuardrailPort,
        profiles: ProfileAssemblerPort,
        contact: ContactPolicyPort,
        mailer: MockEmailService,
        comms: CommunicationRecorderPort,
        audit: AuditLogger,
    ) -> None:
        self._sessions = session_factory
        self._guardrails = guardrails
        self._profiles = profiles
        self._contact = contact
        self._mailer = mailer
        self._comms = comms
        self._audit = audit

    def deliver(self, draft_id: str, *, reviewer_id: str, as_of: date) -> DeliveryResult:
        with self._sessions.begin() as session:
            row = repo.get_draft(session, draft_id)
            state = DraftState(row.state)
            if state == DraftState.DELIVERED:
                raise InvalidStateError("Draft has already been delivered.")
            block_reason, report = self._block_reason(session, row, state, as_of)
            customer_id = row.customer_id

            if block_reason is not None:
                repo.upsert_delivery(
                    session,
                    draft_id=draft_id,
                    status=DeliveryStatus.BLOCKED,
                    block_reason=block_reason,
                )
                if state == DraftState.APPROVED:
                    row.state = str(DraftState.DELIVERY_BLOCKED)
                    row.updated_at = utcnow_iso()
            else:
                recipient = self._profiles.assemble(customer_id, as_of).email
                outbox_path = self._mailer.send(
                    draft_id=draft_id,
                    recipient=recipient,
                    subject=row.subject,
                    body=row.body,
                    metadata={
                        "objective": row.objective,
                        "content_hash": row.content_hash,
                        "approved_by": reviewer_id,
                    },
                )
                delivery = repo.upsert_delivery(
                    session,
                    draft_id=draft_id,
                    status=DeliveryStatus.MOCK_SENT,
                    outbox_path=outbox_path,
                )
                row.state = str(DraftState.DELIVERED)
                row.updated_at = utcnow_iso()
                category = self._category(row)
                objective, offer_id, bill_id, stage = (
                    row.objective,
                    row.offer_id,
                    row.bill_id,
                    row.reminder_stage,
                )
                result = DeliveryResult(
                    draft_id=draft_id,
                    status=DeliveryStatus.MOCK_SENT,
                    outbox_path=outbox_path,
                    delivered_at=delivery.delivered_at,
                )

        if report is not None:
            self._audit.log(
                AuditEventType.VALIDATED,
                customer_ref=customer_id,
                draft_id=draft_id,
                payload={
                    "overall": str(report.overall),
                    "validation_run": report.validation_run,
                    "stage": "pre_delivery",
                    "failed_checks": [
                        f.check_id for f in report.findings if f.severity != Severity.PASS
                    ],
                },
            )
        if block_reason is not None:
            self._audit.log(
                AuditEventType.DELIVERY_BLOCKED,
                actor=reviewer_id,
                customer_ref=customer_id,
                draft_id=draft_id,
                payload={"reason": block_reason, "state_at_attempt": str(state)},
            )
            error = NotApprovedError if block_reason == NOT_APPROVED else DeliveryBlockedError
            raise error(
                "Delivery refused by the delivery gate.",
                details={"draft_id": draft_id, "block_reason": block_reason},
            )

        self._comms.record(
            customer_id,
            CommRecord(
                comm_id=f"CM-{draft_id}",
                sent_at=utcnow(),
                channel="EMAIL",
                category=category,
                objective=objective,
                reminder_stage=stage,
                related_bill_id=bill_id,
                offer_id=offer_id,
                draft_id=draft_id,
                source="MOCK_DELIVERY",
            ),
        )
        self._audit.log(
            AuditEventType.DELIVERED,
            actor=reviewer_id,
            customer_ref=customer_id,
            draft_id=draft_id,
            payload={"status": str(DeliveryStatus.MOCK_SENT), "objective": objective},
        )
        return result

    # ---- checks --------------------------------------------------------------------------
    @staticmethod
    def _category(row) -> MessageCategory:  # noqa: ANN001
        strategy = (row.policy_decisions or {}).get("strategy") or {}
        return MessageCategory(strategy.get("category") or MessageCategory.MARKETING)

    def _block_reason(
        self,
        session: Session,
        row,
        state: DraftState,
        as_of: date,  # noqa: ANN001
    ) -> tuple[str | None, ValidationReport | None]:
        """(first failing check as a reason code or None, the pre-delivery validation report)."""
        if state != DraftState.APPROVED:
            return NOT_APPROVED, None

        approval = repo.latest_action(session, row.draft_id, ReviewerActionType.APPROVE)
        if (
            approval is None
            or approval.content_hash != row.content_hash
            or compute_content_hash(row.subject, row.body) != row.content_hash
        ):
            return "HASH_MISMATCH", None

        report = self._guardrails.validate(rendered_from_row(row), validation_context_from_row(row))
        report = report.model_copy(update={"validation_run": row.validation_run + 1})
        row.validation_run = report.validation_run
        row.validation_status = str(report.overall)
        repo.add_findings(session, row.draft_id, report)
        if report.overall in (Severity.BLOCK, Severity.ESCALATE):
            failed = sorted({f.check_id for f in report.findings if f.severity.rank >= 2})
            return "VALIDATION_FAILED:" + ",".join(failed), report

        profile = self._profiles.assemble(row.customer_id, as_of)
        contact = self._contact.check(profile, self._category(row))
        if not contact.allowed:
            return "CONTACT_NOT_ALLOWED:" + ",".join(contact.reasons), report

        if not profile.email.lower().endswith(ALLOWED_RECIPIENT_DOMAIN):
            return "RECIPIENT_NOT_SYNTHETIC", report
        return None, report
