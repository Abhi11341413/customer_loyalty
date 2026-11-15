"""Request/response wrappers, ErrorResponse.

Owner: SHARED. Drafted by M4 for CP0 from blueprint section 11; needs approval.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.classification import ClassificationResult
from app.schemas.customer import CUSTOMER_ID_PATTERN
from app.schemas.enums import DraftRequestStatus, MessageCategory, RejectionReason
from app.schemas.policy import BillingDecision, ContactDecision, OfferDecision, StrategyDecision
from app.schemas.review import DraftView, Rubric
from app.schemas.validation import ValidationReport

# Pseudonymous reviewer ids such as "rev-01"; no '@' so an email can never be used.
REVIEWER_ID_PATTERN = r"^[A-Za-z0-9_-]{2,32}$"


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    error: ErrorBody
    correlation_id: str


class HealthResponse(BaseModel):
    status: str
    db: str
    llm_mode: str
    model_id: str
    ruleset_version: str
    pipeline_stubs: bool
    as_of_date: date


class AnalysisResponse(BaseModel):
    """Sections B/C of the UI: why this customer gets this strategy."""

    classification: ClassificationResult
    billing: BillingDecision
    offers: OfferDecision
    contact: dict[MessageCategory, ContactDecision]
    strategy: StrategyDecision


class DraftCreateRequest(_Request):
    customer_id: str = Field(pattern=CUSTOMER_ID_PATTERN)
    as_of_date: date | None = None  # defaults to the configured AS_OF_DATE
    regenerate_of: str | None = None


class DraftResponse(BaseModel):
    status: DraftRequestStatus
    correlation_id: str
    draft: DraftView | None = None
    validation: ValidationReport | None = None
    refusal_reasons: list[str] = []
    analysis: AnalysisResponse | None = None


class DraftEditRequest(_Request):
    reviewer_id: str = Field(pattern=REVIEWER_ID_PATTERN)
    subject: str = Field(min_length=5, max_length=90)
    body: str = Field(min_length=40, max_length=3000)


class ApproveRequest(_Request):
    reviewer_id: str = Field(pattern=REVIEWER_ID_PATTERN)
    content_hash: str
    comment: str | None = Field(default=None, max_length=1000)
    rubric: Rubric | None = None
    acknowledge_warnings: bool = False


class RejectRequest(_Request):
    reviewer_id: str = Field(pattern=REVIEWER_ID_PATTERN)
    reason: RejectionReason
    comment: str | None = Field(default=None, max_length=1000)
    rubric: Rubric | None = None


class DeliverRequest(_Request):
    reviewer_id: str = Field(pattern=REVIEWER_ID_PATTERN)


class AuditEventView(BaseModel):
    event_id: str
    ts: datetime
    event_type: str
    actor: str
    customer_ref: str
    draft_id: str | None = None
    payload: dict[str, Any] = {}
    correlation_id: str
