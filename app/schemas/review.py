"""DraftView, ReviewerAction, DeliveryResult.

Owner: SHARED (produced by M4). Drafted by M4 for CP0 from blueprint sections 4.4 (T14-T17),
9.6 and 11.3; needs approval.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import (
    DeliveryStatus,
    DraftState,
    Objective,
    RejectionReason,
    ReviewerActionType,
    Severity,
)
from app.schemas.validation import ValidationReport


class Rubric(BaseModel):
    """Reviewer usefulness rubric, 1-5 per dimension (section 14.5)."""

    model_config = ConfigDict(extra="forbid")

    relevance: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    personalization: int = Field(ge=1, le=5)
    cta: int = Field(ge=1, le=5)
    tone: int = Field(ge=1, le=5)


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model_id: str
    prompt_version: str | None = None
    template: str  # "<template_id>@<template_version>"
    fallback_used: bool = False


class ReviewerAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    draft_id: str
    reviewer_id: str
    action: ReviewerActionType
    content_hash: str
    comment: str | None = None
    rubric: Rubric | None = None
    rejection_reason: RejectionReason | None = None
    created_at: datetime


class DeliveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    status: DeliveryStatus
    block_reason: str | None = None
    outbox_path: str | None = None
    delivered_at: datetime


class DraftView(BaseModel):
    """Everything the reviewer screen needs for one draft."""

    model_config = ConfigDict(extra="forbid")

    draft_id: str
    customer_id: str
    state: DraftState
    objective: Objective
    subject: str
    body: str
    offer_id: str | None = None
    bill_id: str | None = None
    reminder_stage: int | None = None
    facts_used: dict[str, str] = {}
    model: ModelInfo
    content_hash: str
    validation: ValidationReport
    # Snapshot of classification/billing/offers/contact/strategy decisions for evidence display.
    policy_decisions: dict[str, Any] = {}
    reviewer_actions: list[ReviewerAction] = []
    delivery: DeliveryResult | None = None
    # Computed server-side so the UI never decides what is allowed.
    allowed_actions: list[str] = []
    created_at: datetime
    updated_at: datetime


class DraftSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    customer_id: str
    objective: Objective
    model_id: str
    validation_status: Severity
    state: DraftState
    last_reviewer_id: str | None = None
    delivery_status: DeliveryStatus | None = None
    created_at: datetime
    updated_at: datetime
