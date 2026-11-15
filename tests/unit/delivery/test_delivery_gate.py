"""DeliveryGate refusals and the happy path (FR-10)."""

import json
from pathlib import Path

from app.data.models import DraftRow
from app.schemas.customer import ContactPreferences
from tests.conftest import REVIEWER


def _approve(client, draft):
    response = client.post(
        f"/api/v1/drafts/{draft['draft_id']}/approve",
        json={"reviewer_id": REVIEWER, "content_hash": draft["content_hash"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _deliver(client, draft_id):
    return client.post(f"/api/v1/drafts/{draft_id}/deliver", json={"reviewer_id": REVIEWER})


def _events(client, draft_id):
    return [e["event_type"] for e in client.get(f"/api/v1/audit?draft_id={draft_id}").json()]


def test_deliver_before_approval_is_refused_and_recorded(client, make_draft):
    draft = make_draft("C0005")
    response = _deliver(client, draft["draft_id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_APPROVED"

    view = client.get(f"/api/v1/drafts/{draft['draft_id']}").json()
    assert view["state"] == "PENDING_REVIEW"  # unchanged; can still be reviewed
    assert view["delivery"]["status"] == "BLOCKED"
    assert view["delivery"]["block_reason"] == "NOT_APPROVED"
    assert "DELIVERY_BLOCKED" in _events(client, draft["draft_id"])


def test_blocked_draft_delivery_refused(client, make_draft):
    draft = make_draft("C0008")
    response = _deliver(client, draft["draft_id"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_APPROVED"


def test_happy_path_writes_outbox_and_records(client, container, make_draft, settings):
    draft = make_draft("C0005")
    _approve(client, draft)
    response = _deliver(client, draft["draft_id"])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "MOCK_SENT"

    eml = Path(result["outbox_path"])
    assert eml.exists() and eml.parent == settings.outbox_dir
    record = json.loads(eml.with_suffix(".json").read_text(encoding="utf-8"))
    assert record["to"].endswith("@example.test")
    assert record["content_hash"] == draft["content_hash"]

    view = client.get(f"/api/v1/drafts/{draft['draft_id']}").json()
    assert view["state"] == "DELIVERED"
    assert view["allowed_actions"] == []
    assert container.comms.records["C0005"][0].draft_id == draft["draft_id"]
    assert _events(client, draft["draft_id"])[-1] == "DELIVERED"

    again = _deliver(client, draft["draft_id"])
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "INVALID_STATE"


def test_refused_attempt_then_approval_then_delivery(client, make_draft):
    draft = make_draft("C0005")
    assert _deliver(client, draft["draft_id"]).status_code == 409
    _approve(client, draft)
    response = _deliver(client, draft["draft_id"])
    assert response.status_code == 200
    view = client.get(f"/api/v1/drafts/{draft['draft_id']}").json()
    assert view["delivery"]["status"] == "MOCK_SENT"


def test_text_tampered_after_approval_is_blocked(client, container, make_draft):
    draft = make_draft("C0005")
    _approve(client, draft)
    with container.sessions.begin() as session:  # simulate a write that bypassed the API
        session.get(DraftRow, draft["draft_id"]).body += "\nExtra sentence."
    response = _deliver(client, draft["draft_id"])
    assert response.status_code == 409
    assert response.json()["error"]["details"]["block_reason"] == "HASH_MISMATCH"
    view = client.get(f"/api/v1/drafts/{draft['draft_id']}").json()
    assert view["state"] == "DELIVERY_BLOCKED"


def test_consent_withdrawn_after_approval_is_blocked(client, container, make_draft, monkeypatch):
    draft = make_draft("C0005")
    _approve(client, draft)
    from app.pipeline import stubs

    opted_out = ContactPreferences(
        email_service_consent=True, email_marketing_consent=True, email_opt_out=True
    )
    scenario = stubs.SCENARIOS["C0005"]
    monkeypatch.setitem(
        stubs.SCENARIOS,
        "C0005",
        stubs.Scenario(**{**scenario.__dict__, "preferences": opted_out}),
    )
    response = _deliver(client, draft["draft_id"])
    assert response.status_code == 409
    reason = response.json()["error"]["details"]["block_reason"]
    assert reason.startswith("CONTACT_NOT_ALLOWED") and "CONTACT_EMAIL_OPT_OUT" in reason
    assert not any(container.settings.outbox_dir.glob("*.eml"))
