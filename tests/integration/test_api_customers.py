"""API tests for routes_customers (M1) on a demo-seeded in-memory DB."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import routes_customers
from app.data.db import get_session


@pytest.fixture
def client(demo_engine):
    app = FastAPI()
    app.include_router(routes_customers.router)

    def _session():
        with Session(demo_engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    return TestClient(app)


def test_list_sample_customers(client):
    res = client.get("/api/v1/customers?sample=true")
    assert res.status_code == 200
    body = res.json()
    assert [c["customer_id"] for c in body] == [f"C{i:04d}" for i in range(1, 11)]
    assert body[0]["archetype_hint"]


def test_profile_has_features_and_no_email(client):
    res = client.get("/api/v1/customers/C0005/profile?as_of=2026-11-15")
    assert res.status_code == 200
    body = res.json()
    assert body["features"]["current_bill_state"] == "OVERDUE"
    assert "email" not in body["profile"]
    assert "example.test" not in res.text


def test_classify(client):
    res = client.post("/api/v1/customers/C0009/classify", json={"as_of_date": "2026-11-15"})
    assert res.status_code == 200
    body = res.json()
    assert body["segments"] == ["CONSISTENT", "LOYALTY_CANDIDATE", "PAYMENT_REMINDER"]
    assert body["primary_segment"] == "PAYMENT_REMINDER"
    assert body["classification_id"]


def test_unknown_customer_404(client):
    res = client.post("/api/v1/customers/C9998/classify", json={})
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "CUSTOMER_NOT_FOUND"


@pytest.mark.parametrize("cid", ["X1", "C12345", "c0001"])
def test_invalid_id_422(client, cid):
    assert client.get(f"/api/v1/customers/{cid}/profile").status_code == 422


def test_future_as_of_422(client):
    res = client.post("/api/v1/customers/C0001/classify", json={"as_of_date": "2999-01-01"})
    assert res.status_code == 422
