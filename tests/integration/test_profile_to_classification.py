"""M1 integration boundary: seeded DB -> ProfileAssembler -> FeatureBuilder -> classification."""

import json
from datetime import date

import pytest
from sqlalchemy import select

from app.data.models import ClassificationResultRow
from app.data.repositories import SqlBillingReader, SqlOfferReader
from app.features.profile import CustomerNotFoundError
from app.segmentation.service import ClassificationService
from config.settings import DATA_DIR

AS_OF = date(2026, 11, 15)
DEMO = json.loads((DATA_DIR / "seed" / "demo_customers.json").read_text(encoding="utf-8"))
EXPECTED = {c["customer"]["customer_id"]: c["expected"] for c in DEMO["customers"]}


@pytest.mark.parametrize("cid", sorted(EXPECTED))
def test_demo_scenarios(demo_session, cid):
    out = ClassificationService.from_session(demo_session).classify(cid, AS_OF, persist=False)
    exp = EXPECTED[cid]
    assert [s.value for s in out.result.segments] == exp["segments"]
    assert out.result.engagement_segment.value == exp["engagement"]
    for code in exp.get("reason_codes_include", []):
        assert code in [r.code for r in out.result.reason_codes]


def test_specific_demo_facts(demo_session):
    svc = ClassificationService.from_session(demo_session)
    c5 = svc.classify("C0005", AS_OF, persist=False).features
    assert (c5.days_overdue, c5.outstanding_minor) == (5, 59900)
    c6 = svc.classify("C0006", AS_OF, persist=False).features
    assert c6.days_overdue == 26
    c4 = svc.classify("C0004", AS_OF, persist=False).features
    assert c4.days_since_last_activity == 92
    c2 = svc.classify("C0002", AS_OF, persist=False).features
    assert c2.tenure_months == 31 and c2.active_plan_ids == ["PL-POST-499"]


def test_classification_is_persisted_without_pii(demo_session):
    out = ClassificationService.from_session(demo_session).classify("C0002", AS_OF)
    row = demo_session.scalar(select(ClassificationResultRow).where(
        ClassificationResultRow.classification_id == out.result.classification_id))  # fmt: skip
    assert row is not None and row.primary_segment == "LOYALTY_CANDIDATE"
    assert "example.test" not in row.features_snapshot
    assert "Asha" not in row.features_snapshot


def test_unknown_customer(demo_session):
    with pytest.raises(CustomerNotFoundError):
        ClassificationService.from_session(demo_session).classify("C9998", AS_OF)


def test_profile_respects_as_of(demo_session):
    """Classifying as of an earlier date must not see later bills or payments."""
    svc = ClassificationService.from_session(demo_session)
    profile, features = svc.profile_and_features("C0005", date(2026, 11, 5))
    assert all(b.issue_date <= date(2026, 11, 5) for b in profile.bills)
    assert features.current_bill_state.value == "NOT_YET_DUE"  # Oct bill due 10 Nov


def test_readers_for_policy_engine(demo_session):
    offers = {o.offer_id: o for o in SqlOfferReader(demo_session).offers()}
    assert offers["OFF-LOY-200"].eligible_plan_ids
    assert offers["OFF-LOY-200"].eligible_segments == ["LOYALTY_CANDIDATE"]
    reminders = SqlBillingReader(demo_session).reminders_for("C0006", AS_OF)
    assert [r.reminder_stage for r in reminders] == [1, 2]
