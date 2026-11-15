"""FastAPI dependencies (pull services from the container).

Owner: M4.
"""

from __future__ import annotations

from fastapi import Request

from app.audit.logger import AuditLogger
from app.core.container import Container
from app.delivery.gate import DeliveryGate
from app.pipeline.orchestrator import DraftOrchestrator
from app.review.service import ReviewService


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_orchestrator(request: Request) -> DraftOrchestrator:
    return get_container(request).orchestrator


def get_review(request: Request) -> ReviewService:
    return get_container(request).review


def get_delivery(request: Request) -> DeliveryGate:
    return get_container(request).delivery


def get_audit(request: Request) -> AuditLogger:
    return get_container(request).audit
