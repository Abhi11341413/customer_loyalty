"""Contract fixtures other members build against must stay valid and in sync with M1 output."""

import json
from datetime import date

import pytest

from app.schemas.classification import ClassificationResult
from app.schemas.customer import CustomerFeatures, CustomerProfileView
from app.segmentation.service import ClassificationService
from config.settings import PROJECT_ROOT

CONTRACTS = PROJECT_ROOT / "tests" / "fixtures" / "contracts"


@pytest.mark.parametrize("cid", ["C0002", "C0009", "C0010"])
def test_fixtures_validate_and_match_current_output(demo_session, cid):
    profile = CustomerProfileView.model_validate_json(
        (CONTRACTS / f"customer_profile_{cid}.json").read_text(encoding="utf-8")
    )
    features = CustomerFeatures.model_validate_json(
        (CONTRACTS / f"customer_features_{cid}.json").read_text(encoding="utf-8")
    )
    result = ClassificationResult.model_validate_json(
        (CONTRACTS / f"classification_result_{cid}.json").read_text(encoding="utf-8")
    )
    out = ClassificationService.from_session(demo_session).classify(
        cid, date(2026, 11, 15), persist=False
    )
    assert features == out.features
    assert result == out.result
    assert profile.customer_id == cid
    assert "email" not in json.loads(profile.model_dump_json())
