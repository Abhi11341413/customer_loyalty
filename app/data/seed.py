"""Load the catalogue, demo fixtures and synthetic CSV splits into SQLite.

Owner: M1.

Usage:
    python -m app.data.seed --split dev      # catalogue + demo C0001-C0010 + data/synthetic/dev
    python -m app.data.seed --split demo     # catalogue + demo only
    python -m app.data.seed --split eval --db sqlite:///data/eval.db

Every load recreates the tables (the DB is disposable; the files are the source of truth).
"""

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, Integer
from sqlalchemy.orm import Session

from app.data import models as m
from app.data.db import make_engine
from config.settings import DATA_DIR, get_settings

log = logging.getLogger(__name__)

SEED_DIR = DATA_DIR / "seed"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
DEMO_FILE = SEED_DIR / "demo_customers.json"

# Insert order respects foreign keys.
TABLES: list[tuple[str, type[m.Base]]] = [
    ("plans", m.Plan),
    ("campaigns", m.CampaignRow),
    ("campaign_offers", m.CampaignOfferRow),
    ("offer_plan_eligibility", m.OfferPlanEligibility),
    ("customers", m.Customer),
    ("customer_contact_preferences", m.CustomerContactPreferences),
    ("customer_plans", m.CustomerPlan),
    ("customer_activity_monthly", m.CustomerActivityMonthly),
    ("billing_records", m.BillingRecordRow),
    ("payments", m.PaymentRow),
    ("offer_redemptions", m.OfferRedemptionRow),
    ("communication_history", m.CommunicationHistoryRow),
]
CATALOGUE_TABLES = ["plans", "campaigns", "campaign_offers", "offer_plan_eligibility"]
# Keys used per customer inside demo_customers.json
DEMO_KEYS = {
    "customer": "customers",
    "contact_preferences": "customer_contact_preferences",
}


class SeedError(RuntimeError):
    pass


def _coerce(model: type[m.Base], row: dict[str, Any]) -> dict[str, Any]:
    """Turn CSV strings into column types; empty string -> None."""
    out: dict[str, Any] = {}
    cols = model.__table__.columns
    for key, value in row.items():
        if key not in cols:
            raise SeedError(f"{model.__tablename__}: unknown column {key!r}")
        if value == "" or value is None:
            out[key] = None
        elif isinstance(cols[key].type, Integer) and not isinstance(value, int):
            out[key] = int(value)
        else:
            out[key] = value
    return out


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_catalogue(seed_dir: Path = SEED_DIR) -> dict[str, list[dict[str, Any]]]:
    return {t: read_csv(seed_dir / f"{t}.csv") for t in CATALOGUE_TABLES}


def read_demo(path: Path = DEMO_FILE) -> dict[str, list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    tables: dict[str, list[dict[str, Any]]] = {}
    for cust in data["customers"]:
        for key, rows in cust.items():
            if key in ("scenario", "expected"):
                continue
            table = DEMO_KEYS.get(key, key)
            tables.setdefault(table, []).extend(rows if isinstance(rows, list) else [rows])
    return tables


def read_split(split: str) -> dict[str, list[dict[str, Any]]]:
    folder = SYNTHETIC_DIR / split
    if not folder.exists():
        raise SeedError(
            f"{folder} not found — run: python data/synthetic/generate.py --split {split}"
        )
    return {t: read_csv(folder / f"{t}.csv") for t, _ in TABLES if t not in CATALOGUE_TABLES}


def _merge(*parts: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    merged: dict[str, list[dict[str, Any]]] = {}
    for part in parts:
        for table, rows in part.items():
            merged.setdefault(table, []).extend(rows)
    return merged


def load_tables(session: Session, tables: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """Insert rows table by table (FK order). Refuses non-synthetic customers."""
    counts: dict[str, int] = {}
    for name, model in TABLES:
        rows = tables.get(name, [])
        for row in rows:
            values = _coerce(model, row)
            if name == "customers":
                values.setdefault("is_synthetic", 1)
                if values["is_synthetic"] != 1 or not values["email"].endswith("@example.test"):
                    raise SeedError(f"Refusing non-synthetic customer {values['customer_id']}")
            session.add(model(**values))
        session.flush()
        counts[name] = len(rows)
    session.commit()
    return counts


def build_dataset(split: str) -> dict[str, list[dict[str, Any]]]:
    parts = [read_catalogue(), read_demo()]
    if split != "demo":
        parts.append(read_split(split))
    return _merge(*parts)


def seed(split: str, engine: Engine) -> dict[str, int]:
    m.Base.metadata.drop_all(engine)
    m.Base.metadata.create_all(engine)
    with Session(engine) as session:
        return load_tables(session, build_dataset(split))


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the SQLite database.")
    parser.add_argument("--split", choices=["demo", "dev", "eval"], default="dev")
    parser.add_argument("--db", default=None, help="SQLAlchemy URL (default: DATABASE_URL)")
    args = parser.parse_args()
    url = args.db or get_settings().database_url
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    counts = seed(args.split, make_engine(url))
    for table, n in counts.items():
        print(f"{table:32s} {n:6d}")
    print(f"Seeded split={args.split} into {url}")


if __name__ == "__main__":
    main()
