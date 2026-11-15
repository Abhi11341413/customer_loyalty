"""Shared fixtures: in-memory SQLite, config, feature/profile builders.

Owner: ALL. Add your fixtures here in small PRs; keep them generic.
"""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.data.db import make_engine
from app.data.seed import seed
from app.schemas.customer import CustomerFeatures
from app.schemas.enums import AccountStatus, BillState
from app.segmentation.config import SegmentationConfig, default_config

AS_OF = date(2026, 11, 15)


@pytest.fixture(scope="session")
def seg_config() -> SegmentationConfig:
    return default_config()


@pytest.fixture(scope="session")
def demo_engine() -> Engine:
    """Fresh in-memory DB seeded with the catalogue + demo customers C0001-C0010."""
    engine = make_engine("sqlite://")
    seed("demo", engine)
    return engine


@pytest.fixture
def demo_session(demo_engine: Engine) -> Iterator[Session]:
    with Session(demo_engine) as s:
        yield s


def _make_features(**overrides) -> CustomerFeatures:
    """A clearly CONSISTENT, non-loyal, paid-up customer; override any field."""
    base = dict(
        customer_id="C9999",
        as_of_date=AS_OF,
        account_status=AccountStatus.ACTIVE,
        tenure_months=8,
        active_plan_count=1,
        active_plan_ids=["PL-POST-499"],
        months_observed=6,
        active_months_last_6=6,
        recent_activity_avg=30.0,
        prior_activity_avg=30.0,
        activity_trend_ratio=1.0,
        activity_cv_6m=0.1,
        days_since_last_activity=2,
        bills_last_12m=8,
        on_time_bills_last_12m=8,
        on_time_payment_rate_12m=1.0,
        late_payments_last_6m=0,
        current_bill_state=BillState.PAID,
        current_bill_id="B-C9999-2026-10",
    )
    base.update(overrides)
    return CustomerFeatures(**base)


@pytest.fixture
def make_features():
    """Factory fixture: make_features(tenure_months=31, ...) -> CustomerFeatures."""
    return _make_features
