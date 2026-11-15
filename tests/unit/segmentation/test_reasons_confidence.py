import shutil

import pytest
from pydantic import ValidationError

from app.schemas.enums import ConfidenceBand, Segment
from app.segmentation.config import load_config
from app.segmentation.engine import SegmentationEngine
from app.segmentation.reasons import ReasonCodeBuilder, UnknownReasonCodeError
from app.segmentation.rules import flag
from config.settings import POLICIES_DIR


@pytest.fixture(scope="module")
def engine():
    return SegmentationEngine()


def test_every_reason_code_has_a_template(engine, make_features):
    from app.schemas.enums import BillState

    cases = [
        make_features(), make_features(tenure_months=30),
        make_features(days_since_last_activity=90),
        make_features(activity_trend_ratio=0.3, prior_activity_avg=40.0, recent_activity_avg=12.0),
        make_features(current_bill_state=BillState.PARTIALLY_PAID_OVERDUE, days_overdue=3,
                      outstanding_minor=100),
        make_features(tenure_months=1, months_observed=1),
        make_features(activity_cv_6m=0.9),
    ]  # fmt: skip
    for f in cases:
        for rc in engine.classify(f).reason_codes:
            assert rc.text and "{" not in rc.text, rc


def test_unknown_reason_code_raises():
    with pytest.raises(UnknownReasonCodeError):
        ReasonCodeBuilder({}).one(flag("x", 1, True, "NOT_A_CODE"), Segment.STANDARD)


def test_clear_case_is_high_confidence(engine, make_features):
    r = engine.classify(make_features(days_since_last_activity=120))
    assert r.confidence == 1.0 and r.confidence_band == ConfidenceBand.HIGH


def test_borderline_dormant_is_flagged(engine, make_features):
    """61 days, threshold 60, tolerance 30 -> tiny margin -> LOW confidence."""
    r = engine.classify(make_features(days_since_last_activity=61))
    assert r.segments == [Segment.DORMANT]
    assert r.confidence_band == ConfidenceBand.LOW


def test_missing_relevant_feature_lowers_confidence(engine, make_features):
    full = engine.classify(make_features(tenure_months=1, months_observed=1))
    partial = engine.classify(
        make_features(
            tenure_months=1,
            months_observed=1,
            activity_cv_6m=None,
            prior_activity_avg=None,
            activity_trend_ratio=None,
            missing_features=["activity_cv_6m", "prior_activity_avg", "activity_trend_ratio"],
        )
    )
    assert partial.confidence < full.confidence


def test_ruleset_version_recorded(engine, make_features):
    assert engine.classify(make_features()).ruleset_version.startswith("segments.yaml@")


def test_yaml_typo_fails_loudly(tmp_path):
    for name in ("segments.yaml", "reason_codes.yaml"):
        shutil.copy(POLICIES_DIR / name, tmp_path / name)
    seg = tmp_path / "segments.yaml"
    seg.write_text(seg.read_text(encoding="utf-8").replace(
        "min_inactive_days:", "min_inactive_dayz:"), encoding="utf-8")  # fmt: skip
    with pytest.raises(ValidationError):
        load_config(tmp_path)


def test_thresholds_are_configurable(tmp_path, make_features):
    for name in ("segments.yaml", "reason_codes.yaml"):
        shutil.copy(POLICIES_DIR / name, tmp_path / name)
    seg = tmp_path / "segments.yaml"
    seg.write_text(seg.read_text(encoding="utf-8").replace(
        "min_inactive_days: 60", "min_inactive_days: 90"), encoding="utf-8")  # fmt: skip
    cfg = load_config(tmp_path)
    f = make_features(days_since_last_activity=70)
    assert SegmentationEngine(cfg).classify(f).segments == [Segment.CONSISTENT]
    assert SegmentationEngine().classify(f).segments == [Segment.DORMANT]
    assert cfg.ruleset_version != load_config().ruleset_version
