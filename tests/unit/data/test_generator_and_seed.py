import importlib.util
import json
import random
import sys

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.data.db import make_engine
from app.data.models import Base
from app.data.seed import SeedError, load_tables
from config.settings import DATA_DIR


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location(
        "generate", DATA_DIR / "synthetic" / "generate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["generate"] = mod  # needed for @dataclass
    spec.loader.exec_module(mod)
    return mod


def test_generator_is_deterministic(gen):
    def run(seed):
        rng = random.Random(seed)
        out = []
        for i in range(30):
            arch = rng.choices(list(gen.ARCHETYPE_WEIGHTS), list(gen.ARCHETYPE_WEIGHTS.values()))[0]
            spec, _ = gen.sample(arch, f"C{1000 + i}", rng)
            out.append(gen.build_rows(spec, rng))
        return json.dumps(out, sort_keys=True, default=str)

    assert run(42) == run(42)
    assert run(42) != run(43)


def test_demo_fixture_matches_generator(gen):
    """demo_customers.json must be regenerated after editing demo_specs()."""
    on_disk = json.loads((DATA_DIR / "seed" / "demo_customers.json").read_text(encoding="utf-8"))
    ids = [c["customer"]["customer_id"] for c in on_disk["customers"]]
    assert ids == [f"C{i:04d}" for i in range(1, 11)]
    for s, c in zip(gen.demo_specs(), on_disk["customers"], strict=True):
        rows = gen.build_rows(s)
        assert rows["billing_records"] == c["billing_records"], s.customer_id
        assert rows["customer_activity_monthly"] == c["customer_activity_monthly"], s.customer_id


def test_names_and_emails_are_synthetic(gen):
    rows = gen.build_rows(gen.demo_specs()[0])
    assert rows["customers"][0]["email"].endswith("@example.test")


def _empty_session():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def _customer(**kw):
    row = {"customer_id": "C0001", "first_name": "A", "email": "a.c0001@example.test",
           "customer_since": "2025-01-01", "account_status": "ACTIVE", "is_synthetic": 1,
           "created_at": "2026-11-01T00:00:00Z"}  # fmt: skip
    row.update(kw)
    return row


def test_seed_refuses_non_synthetic_rows():
    with _empty_session() as s, pytest.raises(SeedError):
        load_tables(s, {"customers": [_customer(is_synthetic=0)]})


def test_db_rejects_real_email_domain():
    with _empty_session() as s, pytest.raises((SeedError, IntegrityError)):
        load_tables(s, {"customers": [_customer(email="someone@gmail.com")]})


def test_db_rejects_duplicate_bill_period():
    bill = {"customer_id": "C0001", "billing_period": "2026-10", "issue_date": "2026-10-27",
            "due_date": "2026-11-10", "amount_due_minor": 100, "currency": "INR",
            "status": "UNPAID", "dispute_status": "NONE"}  # fmt: skip
    with _empty_session() as s, pytest.raises(IntegrityError):
        load_tables(
            s,
            {
                "customers": [_customer()],
                "billing_records": [{**bill, "bill_id": "B1"}, {**bill, "bill_id": "B2"}],
            },
        )
