"""Policy YAMLs load, are internally consistent, and invalid configs fail loudly (D7)."""

import shutil

import pytest

from app.policy.config import (
    POLICY_DIR,
    PolicyConfigError,
    load_billing_config,
    load_contact_config,
    load_strategy_config,
)


def test_real_configs_load_with_version_tags():
    b, c, s = load_billing_config(), load_contact_config(), load_strategy_config()
    assert b.version_tag.startswith("billing.yaml@1.0#")
    assert c.version_tag.startswith("contact.yaml@1.0#")
    assert s.version_tag.startswith("strategy.yaml@1.0#")


def test_billing_stage_template_and_tone_match_strategy():
    b, s = load_billing_config(), load_strategy_config()
    assert set(s.billing_stage_objectives) == {st.stage for st in b.reminder_stages}
    for stage in b.reminder_stages:
        oc = s.objectives[s.billing_stage_objectives[stage.stage]]
        assert oc.template_id == stage.template_id
        assert oc.tone == stage.tone


def test_stage_for():
    b = load_billing_config()
    assert [b.stage_for(d) for d in (0, 1, 10, 11, 20, 21, 60, 61)] == [
        None,
        1,
        1,
        2,
        2,
        3,
        3,
        None,
    ]


def _copy_policies(tmp_path):
    for name in ("billing.yaml", "contact.yaml", "strategy.yaml"):
        shutil.copy(POLICY_DIR / name, tmp_path / name)
    return tmp_path


def _edit(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_overlapping_stages_rejected(tmp_path):
    d = _copy_policies(tmp_path)
    _edit(d / "billing.yaml", "min_days_overdue: 11", "min_days_overdue: 9")
    with pytest.raises(PolicyConfigError, match="contiguous"):
        load_billing_config.__wrapped__(d)


def test_unknown_key_rejected(tmp_path):
    d = _copy_policies(tmp_path)
    _edit(d / "billing.yaml", "grace_days: 0", "grace_dayz: 0")
    with pytest.raises(PolicyConfigError):
        load_billing_config.__wrapped__(d)


def test_unknown_consent_flag_rejected(tmp_path):
    d = _copy_policies(tmp_path)
    _edit(d / "contact.yaml", "[email_marketing_consent]", "[email_marketting_consent]")
    with pytest.raises(PolicyConfigError, match="unknown consent flags"):
        load_contact_config.__wrapped__(d)


def test_unknown_cta_rejected(tmp_path):
    d = _copy_policies(tmp_path)
    _edit(d / "strategy.yaml", "cta_key: come_back", "cta_key: nope")
    with pytest.raises(PolicyConfigError, match="unknown cta_key"):
        load_strategy_config.__wrapped__(d)


def test_unknown_objective_rejected(tmp_path):
    d = _copy_policies(tmp_path)
    _edit(d / "strategy.yaml", "objective: WINBACK", "objective: WIN_BACK")
    with pytest.raises(PolicyConfigError):
        load_strategy_config.__wrapped__(d)


def test_missing_file_rejected(tmp_path):
    with pytest.raises(PolicyConfigError, match="not found"):
        load_billing_config.__wrapped__(tmp_path)


def test_billing_window_matches_m1_feature_settings():
    """M1's classification flag and M2's reminder decision must use the same bill window."""
    from app.segmentation.config import default_config

    feats, b = default_config().features, load_billing_config()
    assert b.grace_days == feats.grace_days
    assert b.bill_lookback_months == feats.bill_lookback_months
