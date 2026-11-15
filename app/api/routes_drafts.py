"""Drafts, review, delivery endpoints.

Owner: M4. Routers only translate HTTP <-> service calls; no business logic here.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import get_container, get_delivery, get_orchestrator, get_review
from app.core.errors import AppError
from app.delivery.gate import DeliveryGate
from app.pipeline.orchestrator import DraftOrchestrator
from app.review.service import ReviewService
from app.schemas.api import (
    ApproveRequest,
    DeliverRequest,
    DraftCreateRequest,
    DraftEditRequest,
    DraftResponse,
    ErrorResponse,
    RejectRequest,
)
from app.schemas.enums import DraftRequestStatus, DraftState
from app.schemas.review import DeliveryResult, DraftSummary, DraftView
from app.schemas.validation import ValidationReport

router = APIRouter(prefix="/api/v1/drafts", tags=["drafts"])

_ERRORS = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def _resolve_as_of(request: Request, requested: date | None) -> date:
    configured: date = get_container(request).settings.as_of_date
    as_of = requested or configured
    if as_of > date.today():
        raise AppError("as_of_date must not be in the future.", details={"as_of_date": str(as_of)})
    return as_of


@router.post(
    "",
    response_model=DraftResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": DraftResponse, "description": "Refused or escalated"}, **_ERRORS},
)
def create_draft(
    body: DraftCreateRequest,
    request: Request,
    response: Response,
    orchestrator: DraftOrchestrator = Depends(get_orchestrator),
) -> DraftResponse:
    """FR-04: run the full pipeline. Refused/escalated requests return 200 with reasons."""
    as_of = _resolve_as_of(request, body.as_of_date)
    result = orchestrator.create_draft(body.customer_id, as_of, regenerate_of=body.regenerate_of)
    if result.status != DraftRequestStatus.CREATED:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("", response_model=list[DraftSummary])
def list_drafts(
    customer_id: str | None = Query(default=None, pattern=r"^C\d{4}$"),
    state: DraftState | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    review: ReviewService = Depends(get_review),
) -> list[DraftSummary]:
    return review.list(customer_id=customer_id, state=state, limit=limit)


@router.get("/{draft_id}", response_model=DraftView, responses=_ERRORS)
def get_draft(draft_id: str, review: ReviewService = Depends(get_review)) -> DraftView:
    return review.get(draft_id)


@router.patch("/{draft_id}", response_model=DraftView, responses=_ERRORS)
def edit_draft(
    draft_id: str, body: DraftEditRequest, review: ReviewService = Depends(get_review)
) -> DraftView:
    """FR-08: reviewer edit; always re-validated, and invalidates any prior approval."""
    return review.edit(draft_id, reviewer_id=body.reviewer_id, subject=body.subject, body=body.body)


@router.post("/{draft_id}/validate", response_model=ValidationReport, responses=_ERRORS)
def revalidate_draft(
    draft_id: str, review: ReviewService = Depends(get_review)
) -> ValidationReport:
    return review.revalidate(draft_id)


@router.post("/{draft_id}/approve", response_model=DraftView, responses=_ERRORS)
def approve_draft(
    draft_id: str, body: ApproveRequest, review: ReviewService = Depends(get_review)
) -> DraftView:
    return review.approve(
        draft_id,
        reviewer_id=body.reviewer_id,
        content_hash=body.content_hash,
        comment=body.comment,
        rubric=body.rubric,
        acknowledge_warnings=body.acknowledge_warnings,
    )


@router.post("/{draft_id}/reject", response_model=DraftView, responses=_ERRORS)
def reject_draft(
    draft_id: str, body: RejectRequest, review: ReviewService = Depends(get_review)
) -> DraftView:
    return review.reject(
        draft_id,
        reviewer_id=body.reviewer_id,
        reason=body.reason,
        comment=body.comment,
        rubric=body.rubric,
    )


@router.post("/{draft_id}/deliver", response_model=DeliveryResult, responses=_ERRORS)
def deliver_draft(
    draft_id: str,
    body: DeliverRequest,
    request: Request,
    gate: DeliveryGate = Depends(get_delivery),
) -> DeliveryResult:
    """FR-10: mock delivery behind the delivery gate's final re-check."""
    as_of = get_container(request).settings.as_of_date
    return gate.deliver(draft_id, reviewer_id=body.reviewer_id, as_of=as_of)
