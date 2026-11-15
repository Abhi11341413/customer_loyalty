"""Shared fixtures: in-memory SQLite, FakeLLM, contract fixtures.

Owner: ALL. M4 fixtures: an isolated container (in-memory DB, temp outbox, scripted stub
pipeline) and a FastAPI TestClient on top of it.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.container import Container, build_container
from app.main import create_app
from config.settings import Settings

REVIEWER = "rev-01"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        as_of_date=date(2026, 11, 15),
        llm_provider="template",
        outbox_dir=tmp_path / "outbox",
        pipeline_stubs=True,
    )


@pytest.fixture
def container(settings: Settings) -> Container:
    return build_container(settings)


@pytest.fixture
def client(container: Container) -> TestClient:
    logging.getLogger().setLevel(logging.WARNING)
    return TestClient(create_app(container))


@pytest.fixture
def make_draft(client: TestClient):
    """Create a draft for a demo customer and return the draft view (asserts CREATED)."""

    def _make(customer_id: str) -> dict:
        response = client.post("/api/v1/drafts", json={"customer_id": customer_id})
        assert response.status_code == 201, response.text
        return response.json()["draft"]

    return _make
