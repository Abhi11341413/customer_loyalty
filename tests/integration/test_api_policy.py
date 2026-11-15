"""API tests for routes_policy (M2) on a demo-seeded in-memory DB."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import routes_policy
from app.data.db import get_session

AS_OF = {"as_of_date": "2026-11-15"}


@pytest.fixture
def client(demo_engine):
    app = FastAPI()
    app.include_router(routes_policy.router)

    def _session():
        with Session(demo_engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    return TestClient(app)


def post(client, path, **body):
    return client.post(f"/api/v1{path}", json={**AS_OF, **body})


def test_billing_check_c0005(client):
    res = post(client, "/policy/billing/check", customer_id="C0005")
    assert res.status_code == 200
    body = res.json()
    assert body["state"] == "OVERDUE" and body["stage"] == 1 and body["reminder_allowed"]
    assert body["verified_facts"]["amount_due"] == "₹599.00"
    assert body["verified_facts"]["due_date"] == "10 Nov 2026"


def test_offers_check_c0009_reward_deferred(client):
    res = post(client, "/policy/offers/check", customer_id="C0009")
    assert res.status_code == 200
    rejected = {e["offer_id"]: e["failed_checks"] for e in res.json()["rejected"]}
    assert rejected["OFF-LOY-200"] == ["OFFER_BLOCKED_BY_BILLING"]
    assert res.json()["eligible"] == []


def test_offers_check_with_candidates(client):
    res = post(client, "/policy/offers/check", customer_id="C0002",
               candidate_offer_ids=["OFF-LOY-200", "OFF-NOPE"])  # fmt: skip
    body = res.json()
    assert [e["offer_id"] for e in body["eligible"]] == ["OFF-LOY-200"]
    assert body["eligible"][0]["offer"]["value_display"] == "₹200 bill credit"
    assert body["rejected"] == [
        {"offer_id": "OFF-NOPE", "eligible": False, "failed_checks": ["OFFER_NOT_FOUND"],
         "offer": None}
    ]  # fmt: skip


def test_offers_check_rejects_malformed_offer_id(client):
    res = post(client, "/policy/offers/check", customer_id="C0002", candidate_offer_ids=["bad"])
    assert res.status_code == 422


def test_contact_check_c0007_opted_out(client):
    res = post(client, "/policy/contact/check", customer_id="C0007", category="MARKETING")
    assert res.status_code == 200
    body = res.json()
    assert body["allowed"] is False and "CONTACT_EMAIL_OPT_OUT" in body["reasons"]


def test_contact_check_requires_valid_category(client):
    res = post(client, "/policy/contact/check", customer_id="C0001", category="SMS_SPAM")
    assert res.status_code == 422


def test_strategy_select_c0002(client):
    res = post(client, "/strategy/select", customer_id="C0002")
    assert res.status_code == 200
    body = res.json()
    assert body["objective"] == "LOYALTY_REWARD"
    assert body["allowed_offer"]["offer_id"] == "OFF-LOY-200"


def test_analysis_c0010_escalates_with_full_evidence(client):
    res = post(client, "/analysis", customer_id="C0010")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"classification", "billing", "offers", "contact", "strategy"}
    assert body["strategy"]["objective"] == "ESCALATE"
    assert body["billing"]["state"] == "DISPUTED"
    assert set(body["contact"]) == {"SERVICE", "MARKETING"}


def test_analysis_never_leaks_email(client):
    res = post(client, "/analysis", customer_id="C0005")
    assert "example.test" not in res.text


def test_default_as_of_date_is_used(client):
    res = client.post("/api/v1/strategy/select", json={"customer_id": "C0005"})
    assert res.status_code == 200


def test_unknown_customer_404(client):
    res = post(client, "/analysis", customer_id="C9998")
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "CUSTOMER_NOT_FOUND"


@pytest.mark.parametrize("cid", ["X1", "C12345", "c0001"])
def test_invalid_customer_id_422(client, cid):
    assert post(client, "/strategy/select", customer_id=cid).status_code == 422


def test_future_as_of_422(client):
    res = client.post("/api/v1/analysis", json={"customer_id": "C0005", "as_of_date": "2099-01-01"})
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "AS_OF_IN_FUTURE"


def test_client_sent_decisions_are_rejected(client):
    """The server recomputes everything; extra fields such as a forged strategy are refused."""
    res = post(client, "/strategy/select", customer_id="C0005", objective="LOYALTY_REWARD")
    assert res.status_code == 422
