"""httpx wrapper for the backend API.

Owner: M4. The UI never decides eligibility, validation or what is allowed; it only calls the
API and renders responses. Errors are converted to ApiError with a friendly message.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_TIMEOUT_S = 30.0

FRIENDLY = {
    "CUSTOMER_NOT_FOUND": "No customer with that ID.",
    "DRAFT_NOT_FOUND": "That draft no longer exists.",
    "HASH_MISMATCH": "The draft changed since you reviewed it. Reload and review it again.",
    "VALIDATION_BLOCKED": "This draft failed mandatory checks and cannot be approved.",
    "WARNINGS_NOT_ACKNOWLEDGED": "Tick 'I have reviewed the warnings' before approving.",
    "DUPLICATE_PENDING_DRAFT": "This customer already has an open draft.",
    "NOT_APPROVED": "Delivery refused: the draft is not approved.",
    "DELIVERY_BLOCKED": "Delivery refused by the final safety re-check.",
    "INVALID_STATE": "That action is not allowed in the draft's current state.",
    "COMPONENT_NOT_READY": "Part of the pipeline is not implemented yet.",
    "REQUEST_INVALID": "Some fields are invalid.",
    "BACKEND_UNREACHABLE": "Cannot reach the backend. Is `uvicorn app.main:app` running?",
}

#: Shown when M1's GET /api/v1/customers is not available yet.
FALLBACK_CUSTOMERS = [
    {"customer_id": "C0001", "hint": "Consistent"},
    {"customer_id": "C0002", "hint": "Loyalty reward"},
    {"customer_id": "C0003", "hint": "Declining activity"},
    {"customer_id": "C0004", "hint": "Dormant"},
    {"customer_id": "C0005", "hint": "Overdue - courteous"},
    {"customer_id": "C0006", "hint": "Overdue - firm"},
    {"customer_id": "C0007", "hint": "Refusal - opted out"},
    {"customer_id": "C0008", "hint": "Unsafe LLM output"},
    {"customer_id": "C0009", "hint": "Loyal + overdue"},
    {"customer_id": "C0010", "hint": "Escalation - disputed"},
]


@dataclass
class ApiError(Exception):
    status: int
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None

    @property
    def friendly(self) -> str:
        return FRIENDLY.get(self.code, self.message)

    def __str__(self) -> str:
        return f"{self.code}: {self.friendly}"


class ApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("BACKEND_URL", "http://localhost:8000")).rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout_s, transport=transport)

    # ---- low level -----------------------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(0, "BACKEND_UNREACHABLE", str(exc)) from exc
        if response.is_success:
            return response.json()
        try:
            payload = response.json()
            err = payload.get("error", {})
            raise ApiError(
                status=response.status_code,
                code=err.get("code", "HTTP_ERROR"),
                message=err.get("message", response.text),
                details=err.get("details", {}),
                correlation_id=payload.get("correlation_id"),
            )
        except ValueError:
            raise ApiError(response.status_code, "HTTP_ERROR", response.text) from None

    # ---- endpoints -----------------------------------------------------------------------
    def health(self) -> dict:
        return self._request("GET", "/api/v1/health")

    def customers(self) -> list[dict]:
        """Sample customers from M1's endpoint, or the fixed demo list if it is not live yet."""
        try:
            return self._request("GET", "/api/v1/customers", params={"sample": "true"})
        except ApiError as exc:
            if exc.status in (404, 405, 501, 503):
                return FALLBACK_CUSTOMERS
            raise

    def create_draft(
        self, customer_id: str, as_of_date: str | None = None, regenerate_of: str | None = None
    ) -> dict:
        body: dict[str, Any] = {"customer_id": customer_id}
        if as_of_date:
            body["as_of_date"] = as_of_date
        if regenerate_of:
            body["regenerate_of"] = regenerate_of
        return self._request("POST", "/api/v1/drafts", json=body)

    def get_draft(self, draft_id: str) -> dict:
        return self._request("GET", f"/api/v1/drafts/{draft_id}")

    def list_drafts(self, customer_id: str | None = None, state: str | None = None) -> list[dict]:
        params = {k: v for k, v in {"customer_id": customer_id, "state": state}.items() if v}
        return self._request("GET", "/api/v1/drafts", params=params)

    def edit_draft(self, draft_id: str, reviewer_id: str, subject: str, body: str) -> dict:
        return self._request(
            "PATCH",
            f"/api/v1/drafts/{draft_id}",
            json={"reviewer_id": reviewer_id, "subject": subject, "body": body},
        )

    def revalidate(self, draft_id: str) -> dict:
        return self._request("POST", f"/api/v1/drafts/{draft_id}/validate")

    def approve(
        self,
        draft_id: str,
        reviewer_id: str,
        content_hash: str,
        comment: str | None = None,
        rubric: dict | None = None,
        acknowledge_warnings: bool = False,
    ) -> dict:
        return self._request(
            "POST",
            f"/api/v1/drafts/{draft_id}/approve",
            json={
                "reviewer_id": reviewer_id,
                "content_hash": content_hash,
                "comment": comment or None,
                "rubric": rubric,
                "acknowledge_warnings": acknowledge_warnings,
            },
        )

    def reject(
        self,
        draft_id: str,
        reviewer_id: str,
        reason: str,
        comment: str | None = None,
        rubric: dict | None = None,
    ) -> dict:
        return self._request(
            "POST",
            f"/api/v1/drafts/{draft_id}/reject",
            json={
                "reviewer_id": reviewer_id,
                "reason": reason,
                "comment": comment or None,
                "rubric": rubric,
            },
        )

    def deliver(self, draft_id: str, reviewer_id: str) -> dict:
        return self._request(
            "POST", f"/api/v1/drafts/{draft_id}/deliver", json={"reviewer_id": reviewer_id}
        )

    def audit(
        self,
        customer_id: str | None = None,
        draft_id: str | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        for key, value in (
            ("customer_id", customer_id),
            ("draft_id", draft_id),
            ("correlation_id", correlation_id),
        ):
            if value:
                params[key] = value
        return self._request("GET", "/api/v1/audit", params=params)
