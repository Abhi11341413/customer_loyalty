"""Load and validate segments.yaml + reason_codes.yaml into typed config.

Owner: M1. A typo in the YAML fails loudly at startup (extra keys are forbidden).
`ruleset_version` = "segments.yaml@<sha256 prefix>" over both files, recorded on every result.
"""

import hashlib
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from app.features.builder import FeatureSettings
from app.schemas.enums import BillState, EngagementSegment, Segment
from config.settings import POLICIES_DIR


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InsufficientDataCfg(_Strict):
    min_tenure_months: int
    tolerance_tenure_months: float
    min_months_observed: int
    tolerance_months_observed: float
    critical_features: list[str]


class DormantCfg(_Strict):
    min_inactive_days: int
    tolerance_days: float


class DecliningCfg(_Strict):
    min_prior_activity_avg: float
    tolerance_prior_avg: float
    max_trend_ratio: float
    tolerance_trend_ratio: float


class ConsistentCfg(_Strict):
    min_active_months_last_6: int
    tolerance_active_months: float
    min_trend_ratio: float
    tolerance_trend_ratio: float
    max_activity_cv: float
    tolerance_cv: float
    min_on_time_rate: float
    tolerance_on_time_rate: float


class LoyaltyCfg(_Strict):
    min_tenure_months: int
    tolerance_tenure_months: float
    min_on_time_rate: float
    tolerance_on_time_rate: float
    max_late_payments_last_6m: int
    min_active_plan_count: int


class PaymentReminderCfg(_Strict):
    bill_states: list[BillState]


class SegmentsCfg(_Strict):
    INSUFFICIENT_DATA: InsufficientDataCfg
    DORMANT: DormantCfg
    DECLINING_ACTIVITY: DecliningCfg
    CONSISTENT: ConsistentCfg
    LOYALTY_CANDIDATE: LoyaltyCfg
    PAYMENT_REMINDER: PaymentReminderCfg


class ConfidenceCfg(_Strict):
    high: float
    medium: float


class SegmentationConfig(_Strict):
    version: str
    features: FeatureSettings
    engagement_order: list[EngagementSegment]
    primary_precedence: list[Segment]
    segments: SegmentsCfg
    confidence: ConfidenceCfg
    reason_texts: dict[str, str]
    ruleset_version: str


def load_config(policies_dir: Path = POLICIES_DIR) -> SegmentationConfig:
    seg_path, rc_path = policies_dir / "segments.yaml", policies_dir / "reason_codes.yaml"
    seg_bytes, rc_bytes = seg_path.read_bytes(), rc_path.read_bytes()
    seg = yaml.safe_load(seg_bytes)
    rc = yaml.safe_load(rc_bytes)
    digest = hashlib.sha256(seg_bytes + b"\0" + rc_bytes).hexdigest()[:7]
    return SegmentationConfig(
        **seg, reason_texts=rc["codes"], ruleset_version=f"segments.yaml@{digest}"
    )


@lru_cache
def default_config() -> SegmentationConfig:
    return load_config()
