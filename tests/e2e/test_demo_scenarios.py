"""End-to-end: the section 16 demo scenarios through the HTTP API (stub pipeline).

These pin the M4 flow (orchestrator -> review -> delivery -> audit). When real M1-M3
components replace the stubs, the same expectations must still hold.
"""

import pytest

from tests.conftest import REVIEWER

CREATED_PASS = [
    ("C0001", "APPRECIATION", None),
    ("C0002", "LOYALTY_REWARD", "OFF-LOY-200"),
    ("C0003", "REENGAGEMENT", "OFF-RE-5GB"),
    ("C0004", "WINBACK", "OFF-RE-5GB"),
    ("C0005", "BILLING_REMINDER_COURTEOUS", None),
    ("C0006", "BILLING_REMINDER_FIRM", None),
    ("C0009", "BILLING_REMINDER_FOLLOWUP", None),
]


@pytest.mark.parametrize(("customer_id", "objective", "offer_id"), CREATED_PASS)
def test_drafting_scenarios(client, customer_id, objective, offer_id):
    response = client.post("/api/v1/drafts", json={"customer_id": customer_id})
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "CREATED"
    draft = payload["draft"]
    assert draft["objective"] == objective
    assert draft["offer_id"] == offer_id
    assert draft["state"] == "PENDING_REVIEW"
    assert payload["validation"]["overall"] == "PASS"
    assert "{{" not in draft["body"]
    assert payload["correlation_id"] == response.headers["X-Correlation-ID"]


def test_c0002_reward_uses_verified_offer_facts(client):
    draft = client.post("/api/v1/drafts", json={"customer_id": "C0002"}).json()["draft"]
    assert "₹200 bill credit" in draft["body"] and "31 Dec 2026" in draft["body"]
    assert draft["facts_used"]["offer_value"] == "₹200 bill credit"
    assert "Offer terms:" in draft["body"]


def test_c0009_reward_deferred_while_overdue(client):
    payload = client.post("/api/v1/drafts", json={"customer_id": "C0009"}).json()
    strategy = payload["analysis"]["strategy"]
    assert strategy["allowed_offer"] is None
    assert strategy["suppressed"][0]["objective"] == "LOYALTY_REWARD"
    rejected = payload["analysis"]["offers"]["rejected"][0]
    assert rejected["failed_checks"] == ["OFFER_BLOCKED_BY_BILLING"]
    assert "reward" not in payload["draft"]["body"].lower()


def test_c0007_refused_without_draft(client):
    response = client.post("/api/v1/drafts", json={"customer_id": "C0007"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "REFUSED"
    assert payload["draft"] is None
    assert "CONTACT_EMAIL_OPT_OUT" in payload["refusal_reasons"]
    events = [e["event_type"] for e in client.get("/api/v1/audit?customer_id=C0007").json()]
    assert events[-1] == "REFUSED" and "DRAFT_GENERATED" not in events
    assert client.get("/api/v1/drafts?customer_id=C0007").json() == []


def test_c0008_unsafe_output_blocked_and_undeliverable(client):
    payload = client.post("/api/v1/drafts", json={"customer_id": "C0008"}).json()
    draft = payload["draft"]
    assert draft["state"] == "BLOCKED"
    blocked = {f["check_id"] for f in payload["validation"]["findings"] if f["severity"] == "BLOCK"}
    assert {"OFFER_ID_VALID", "NUMBER_GROUNDED", "DATE_GROUNDED", "BLOCKED_LANGUAGE"} <= blocked
    assert "APPROVE" not in draft["allowed_actions"]
    deliver = client.post(
        f"/api/v1/drafts/{draft['draft_id']}/deliver", json={"reviewer_id": REVIEWER}
    )
    assert deliver.status_code == 409


def test_c0010_escalated_without_draft(client):
    payload = client.post("/api/v1/drafts", json={"customer_id": "C0010"}).json()
    assert payload["status"] == "ESCALATED"
    assert payload["draft"] is None
    assert payload["refusal_reasons"] == ["BILL_DISPUTED"]


def test_full_workflow_edit_approve_deliver(client, settings):
    """C0005: draft -> small edit -> re-validate -> approve -> mock send -> audit trail."""
    draft = client.post("/api/v1/drafts", json={"customer_id": "C0005"}).json()["draft"]
    edited = client.patch(
        f"/api/v1/drafts/{draft['draft_id']}",
        json={
            "reviewer_id": REVIEWER,
            "subject": draft["subject"],
            "body": draft["body"].replace("Hi Ravi,", "Hello Ravi,"),
        },
    ).json()
    assert edited["state"] == "PENDING_REVIEW" and edited["validation"]["overall"] == "PASS"

    approved = client.post(
        f"/api/v1/drafts/{draft['draft_id']}/approve",
        json={
            "reviewer_id": REVIEWER,
            "content_hash": edited["content_hash"],
            "comment": "Friendlier greeting",
        },
    )
    assert approved.status_code == 200

    delivered = client.post(
        f"/api/v1/drafts/{draft['draft_id']}/deliver", json={"reviewer_id": REVIEWER}
    )
    assert delivered.status_code == 200
    assert list(settings.outbox_dir.glob("*.eml"))

    events = [
        e["event_type"] for e in client.get("/api/v1/audit?customer_id=C0005&limit=200").json()
    ]
    assert events == [
        "CLASSIFIED",
        "POLICY_DECIDED",
        "DRAFT_GENERATED",
        "VALIDATED",
        "EDITED",
        "VALIDATED",
        "APPROVED",
        "VALIDATED",
        "DELIVERED",
    ]

    summary = client.get("/api/v1/drafts?customer_id=C0005").json()[0]
    assert summary["state"] == "DELIVERED" and summary["delivery_status"] == "MOCK_SENT"

    # Duplicate outreach: a second reminder right after delivery is refused by contact policy.
    again = client.post("/api/v1/drafts", json={"customer_id": "C0005"}).json()
    assert again["status"] == "REFUSED"
    assert "CONTACT_DUPLICATE_RECENT" in again["refusal_reasons"]


def test_duplicate_open_draft_and_regeneration(client):
    first = client.post("/api/v1/drafts", json={"customer_id": "C0001"}).json()["draft"]
    dup = client.post("/api/v1/drafts", json={"customer_id": "C0001"})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "DUPLICATE_PENDING_DRAFT"
    assert dup.json()["error"]["details"]["open_draft_ids"] == [first["draft_id"]]

    regen = client.post(
        "/api/v1/drafts", json={"customer_id": "C0001", "regenerate_of": first["draft_id"]}
    )
    assert regen.status_code == 201
    old = client.get(f"/api/v1/drafts/{first['draft_id']}").json()
    assert old["state"] == "REJECTED"
    assert regen.json()["draft"]["draft_id"] != first["draft_id"]


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"customer_id": "C9999"}, 404, "CUSTOMER_NOT_FOUND"),
        ({"customer_id": "bad"}, 422, "REQUEST_INVALID"),
        ({"customer_id": "C0001", "as_of_date": "2099-01-01"}, 400, "BAD_REQUEST"),
        ({"customer_id": "C0001", "extra": 1}, 422, "REQUEST_INVALID"),
    ],
)
def test_bad_requests(client, body, status, code):
    response = client.post("/api/v1/drafts", json=body)
    assert response.status_code == status
    error = response.json()
    assert error["error"]["code"] == code
    assert error["correlation_id"]


def test_unknown_draft_404(client):
    response = client.get("/api/v1/drafts/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DRAFT_NOT_FOUND"


def test_health(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok" and body["db"] == "ok"
    assert body["pipeline_stubs"] is True


def test_without_stubs_pipeline_reports_not_ready(settings):
    from fastapi.testclient import TestClient

    from app.core.container import build_container
    from app.main import create_app

    app_client = TestClient(
        create_app(build_container(settings.model_copy(update={"pipeline_stubs": False})))
    )
    assert app_client.get("/api/v1/health").status_code == 200
    response = app_client.post("/api/v1/drafts", json={"customer_id": "C0001"})
    assert response.status_code == 503
    assert response.json()["error"]["details"]["owner"] == "M1"
