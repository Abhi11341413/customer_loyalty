"""Billing/offers/contact/strategy checks and /analysis (CLAUDE.md §11.3, endpoints 5-9).

Owner: M2. No business logic here — routes call ClassificationService (M1) for the
profile/features/classification and PolicyService (M2) for the decisions. The server always
recomputes every decision; it never trusts decisions sent by a client.

M4 registers this router in app/main.py:  app.include_router(routes_policy.router)
Errors use {"code", "message"} in `detail`, like routes_customers (M1); M4's error
middleware maps them to the shared error envelope.

Nothing is persisted by these endpoints (classification uses persist=False): they are
read-only "explain" calls for the UI sections B and C.
"""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.data.db import get_session
from app.features.profile import CustomerNotFoundError
from app.policy.service import PolicyService
from app.schemas.classification import ClassificationResult
from app.schemas.customer import CUSTOMER_ID_PATTERN
from app.schemas.enums import MessageCategory
from app.schemas.policy import BillingDecision, ContactDecision, OfferDecision, StrategyDecision
from app.segmentation.service import ClassificationOutput, ClassificationService
from config.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["policy"])

SessionDep = Annotated[Session, Depends(get_session)]

OFFER_ID_PATTERN = r"^OFF-[A-Z0-9-]+$"


# --------------------------------------------------------------------------- request/response


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PolicyRequest(_Request):
    customer_id: str = Field(pattern=CUSTOMER_ID_PATTERN, examples=["C0005"])
    as_of_date: date | None = None  # defaults to the configured AS_OF_DATE


class OfferCheckRequest(PolicyRequest):
    channel: Literal["EMAIL"] = "EMAIL"
    #: None = evaluate every offer in the catalogue
    candidate_offer_ids: list[Annotated[str, Field(pattern=OFFER_ID_PATTERN)]] | None = None


class ContactCheckRequest(PolicyRequest):
    category: MessageCategory


class AnalysisResponse(BaseModel):
    """Sections B/C of the UI. Same shape as M4's AnalysisResponse (app/schemas/api.py, PR #3);
    once that is merged, import it from there instead."""

    classification: ClassificationResult
    billing: BillingDecision
    offers: OfferDecision
    contact: dict[MessageCategory, ContactDecision]
    strategy: StrategyDecision


# --------------------------------------------------------------------------- helpers


def _resolve_as_of(as_of: date | None) -> date:
    value = as_of or get_settings().as_of_date
    if value > date.today():
        raise HTTPException(
            422, {"code": "AS_OF_IN_FUTURE", "message": "as_of_date must not be in the future"}
        )
    return value


def _classify(session: Session, req: PolicyRequest) -> ClassificationOutput:
    try:
        return ClassificationService.from_session(session).classify(
            req.customer_id, _resolve_as_of(req.as_of_date), persist=False
        )
    except CustomerNotFoundError as exc:
        raise HTTPException(
            404,
            {"code": "CUSTOMER_NOT_FOUND", "message": f"Customer {req.customer_id} not found"},
        ) from exc


# --------------------------------------------------------------------------- endpoints


@router.post("/policy/billing/check", response_model=BillingDecision)
def billing_check(body: PolicyRequest, session: SessionDep) -> BillingDecision:
    """FR-06: bill state, reminder stage and the verified billing facts."""
    out = _classify(session, body)
    return PolicyService.from_session(session).billing.evaluate(out.profile, out.features)


@router.post("/policy/offers/check", response_model=OfferDecision)
def offers_check(body: OfferCheckRequest, session: SessionDep) -> OfferDecision:
    """FR-05: every candidate offer with its failed checks (empty = eligible)."""
    out = _classify(session, body)
    svc = PolicyService.from_session(session)
    billing = svc.billing.evaluate(out.profile, out.features)
    return svc.offers.evaluate(
        out.profile, out.features, out.result, billing, body.channel, body.candidate_offer_ids
    )


@router.post("/policy/contact/check", response_model=ContactDecision)
def contact_check(body: ContactCheckRequest, session: SessionDep) -> ContactDecision:
    """FR-07 (pre-generation): consent, opt-out, preferences, frequency caps."""
    out = _classify(session, body)
    return PolicyService.from_session(session).contact.check(out.profile, body.category)


@router.post("/strategy/select", response_model=StrategyDecision)
def strategy_select(body: PolicyRequest, session: SessionDep) -> StrategyDecision:
    """FR-03: one objective, template, tone, offer and disclaimers — or NO_CONTACT / ESCALATE."""
    out = _classify(session, body)
    return (
        PolicyService.from_session(session).analyze(out.profile, out.features, out.result).strategy
    )


@router.post("/analysis", response_model=AnalysisResponse)
def analysis(body: PolicyRequest, session: SessionDep) -> AnalysisResponse:
    """Endpoints 4-8 in one call, for UI sections B (analysis) and C (strategy & eligibility)."""
    out = _classify(session, body)
    a = PolicyService.from_session(session).analyze(out.profile, out.features, out.result)
    return AnalysisResponse(
        classification=out.result,
        billing=a.billing,
        offers=a.offers,
        contact=a.contact,
        strategy=a.strategy,
    )
