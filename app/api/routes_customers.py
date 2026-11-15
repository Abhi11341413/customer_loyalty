"""Customer endpoints: list, profile + features (FR-01), classify (FR-02).

Owner: M1. No business logic here — it calls ClassificationService.
M4 registers this router in app/main.py:  app.include_router(routes_customers.router)
Errors use {"code", "message"} in `detail`; M4's error middleware can map them to the shared
error envelope.
"""

import json
from datetime import date
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.data.db import get_session
from app.data.repositories.customer_repo import SqlCustomerReader
from app.data.seed import DEMO_FILE
from app.features.profile import CustomerNotFoundError
from app.schemas.classification import ClassificationResult, ClassifyRequest
from app.schemas.customer import (
    CUSTOMER_ID_PATTERN,
    CustomerProfileResponse,
    CustomerProfileView,
    CustomerSummary,
)
from app.segmentation.service import ClassificationService
from config.settings import get_settings

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])

SessionDep = Annotated[Session, Depends(get_session)]
CustomerId = Annotated[str, Path(pattern=CUSTOMER_ID_PATTERN, examples=["C0002"])]


@lru_cache
def _demo_hints() -> dict[str, str]:
    try:
        data = json.loads(DEMO_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {c["customer"]["customer_id"]: c["scenario"] for c in data["customers"]}


def _resolve_as_of(as_of: date | None) -> date:
    value = as_of or get_settings().as_of_date
    if value > date.today():
        raise HTTPException(
            422, {"code": "AS_OF_IN_FUTURE", "message": "as_of_date must not be in the future"}
        )
    return value


def _not_found(customer_id: str) -> HTTPException:
    return HTTPException(
        404, {"code": "CUSTOMER_NOT_FOUND", "message": f"Customer {customer_id} not found"}
    )


@router.get("", response_model=list[CustomerSummary])
def list_customers(
    session: SessionDep, sample: Annotated[bool, Query()] = True
) -> list[CustomerSummary]:
    """sample=true returns only the fixed demo customers (with a scenario hint)."""
    hints = _demo_hints()
    rows = SqlCustomerReader(session).list_customers(sorted(hints) if sample else None)
    return [
        CustomerSummary(
            customer_id=r.customer_id,
            first_name=r.first_name,
            archetype_hint=hints.get(r.customer_id),
        )
        for r in rows
    ]


@router.get("/{customer_id}/profile", response_model=CustomerProfileResponse)
def get_profile(
    customer_id: CustomerId, session: SessionDep, as_of: date | None = None
) -> CustomerProfileResponse:
    svc = ClassificationService.from_session(session)
    try:
        profile, features = svc.profile_and_features(customer_id, _resolve_as_of(as_of))
    except CustomerNotFoundError as exc:
        raise _not_found(customer_id) from exc
    return CustomerProfileResponse(
        profile=CustomerProfileView.from_profile(profile), features=features
    )


@router.post("/{customer_id}/classify", response_model=ClassificationResult)
def classify(
    customer_id: CustomerId, session: SessionDep, body: ClassifyRequest | None = None
) -> ClassificationResult:
    """Classify and persist. INSUFFICIENT_DATA is a normal 200 result, not an error."""
    as_of = _resolve_as_of(body.as_of_date if body else None)
    try:
        return ClassificationService.from_session(session).classify(customer_id, as_of).result
    except CustomerNotFoundError as exc:
        raise _not_found(customer_id) from exc
