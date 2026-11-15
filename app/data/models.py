"""SQLAlchemy ORM tables.

Owner: M1 (changes announced to team).

This file currently holds only the review/delivery/audit tables T14-T18 from the blueprint
(section 4.4), added by M4 because those components depend on them. M1 owns this file:
please add T1-T13 here and then turn the commented foreign keys below into real ones
(drafts.customer_id -> customers, drafts.classification_id -> classification_results,
drafts.offer_id -> campaign_offers, drafts.bill_id -> billing_records).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


_SEVERITIES = "('PASS','WARN','BLOCK','ESCALATE')"


class DraftRow(Base):
    """T14 drafts: draft lifecycle state (one row per generated draft)."""

    __tablename__ = "drafts"
    __table_args__ = (
        CheckConstraint(f"validation_status IN {_SEVERITIES}", name="ck_drafts_validation"),
        CheckConstraint(
            "state IN ('GENERATED','PENDING_REVIEW','BLOCKED','ESCALATED','APPROVED',"
            "'REJECTED','DELIVERED','DELIVERY_BLOCKED','REFUSED')",
            name="ck_drafts_state",
        ),
    )

    draft_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String, index=True)  # FK -> customers (M1)
    classification_id: Mapped[str] = mapped_column(String)  # FK -> classification_results (M1)
    objective: Mapped[str] = mapped_column(String)
    template_id: Mapped[str] = mapped_column(String)
    template_version: Mapped[str] = mapped_column(String)
    prompt_version: Mapped[str | None] = mapped_column(String, nullable=True)
    model_provider: Mapped[str] = mapped_column(String)
    model_id: Mapped[str] = mapped_column(String)
    fallback_used: Mapped[int] = mapped_column(Integer, default=0)
    offer_id: Mapped[str | None] = mapped_column(String, nullable=True)  # FK -> campaign_offers
    bill_id: Mapped[str | None] = mapped_column(String, nullable=True)  # FK -> billing_records
    reminder_stage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    facts_used: Mapped[dict[str, Any]] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String)
    validation_status: Mapped[str] = mapped_column(String)
    validation_run: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String, index=True)
    # Snapshot of classification/billing/offers/contact/strategy + validation context.
    policy_decisions: Mapped[dict[str, Any]] = mapped_column(JSON)
    regenerated_from: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)


class ValidationFindingRow(Base):
    """T15 validation_findings: one row per check result per validation run."""

    __tablename__ = "validation_findings"
    __table_args__ = (CheckConstraint(f"severity IN {_SEVERITIES}", name="ck_findings_severity"),)

    finding_id: Mapped[str] = mapped_column(String, primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.draft_id"), index=True)
    validation_run: Mapped[int] = mapped_column(Integer)
    check_id: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    mandatory: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    span: Mapped[str | None] = mapped_column(String(80), nullable=True)


class ReviewerActionRow(Base):
    """T16 reviewer_actions."""

    __tablename__ = "reviewer_actions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('EDIT','APPROVE','REJECT','ESCALATE')", name="ck_actions_action"
        ),
        CheckConstraint(
            "rejection_reason IS NULL OR rejection_reason IN "
            "('FACTUAL_ERROR','WRONG_TONE','WRONG_STRATEGY','POLICY','OTHER')",
            name="ck_actions_reason",
        ),
    )

    action_id: Mapped[str] = mapped_column(String, primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.draft_id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    content_hash: Mapped[str] = mapped_column(String)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    rubric: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String)


class DeliveryRow(Base):
    """T17 deliveries: one row per draft (a BLOCKED attempt may later become MOCK_SENT)."""

    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('MOCK_SENT','BLOCKED','FAILED')", name="ck_deliveries_status"),
    )

    delivery_id: Mapped[str] = mapped_column(String, primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.draft_id"), unique=True)
    status: Mapped[str] = mapped_column(String)
    block_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    outbox_path: Mapped[str | None] = mapped_column(String, nullable=True)
    delivered_at: Mapped[str] = mapped_column(String)


class AuditEventRow(Base):
    """T18 audit_events: append-only. No names, emails, bodies or raw prompts."""

    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    ts: Mapped[str] = mapped_column(String, index=True)
    event_type: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    customer_ref: Mapped[str] = mapped_column(String, index=True)
    draft_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    correlation_id: Mapped[str] = mapped_column(String, index=True)
