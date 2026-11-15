"""Pure rule functions, one per segment. Thresholds come from segments.yaml.

Owner: M1. Each rule returns a RuleOutcome with a full condition trace, which feeds reason
codes and confidence. Rules reference only allowed features (no names, emails, spend,
location, demographics) — see tests/unit/features/test_no_protected_features.py.
A missing feature value always makes its condition fail (never guessed).
"""

import operator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal

from app.schemas.customer import CustomerFeatures
from app.schemas.enums import BillState, EngagementSegment, Segment
from app.segmentation.config import SegmentationConfig

_OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt}


@dataclass(frozen=True)
class Condition:
    feature: str
    op: str
    value: Any
    threshold: Any
    tolerance: float | None  # None = categorical condition (margin 1 when passed)
    passed: bool
    code: str | None = None  # reason code emitted when this condition supports the segment
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def missing(self) -> bool:
        return self.value is None


@dataclass(frozen=True)
class RuleOutcome:
    segment: Segment
    fired: bool
    mode: Literal["all", "any"]
    conditions: list[Condition]

    @property
    def supporting(self) -> list[Condition]:
        """Conditions that justify the segment (all for 'all' rules, passed ones for 'any')."""
        if not self.fired:
            return []
        return self.conditions if self.mode == "all" else [c for c in self.conditions if c.passed]

    @property
    def features(self) -> set[str]:
        return {c.feature for c in self.conditions}


def compare(
    feature: str,
    value: Any,
    op: str,
    threshold: Any,
    tolerance: float | None,
    code: str | None = None,
    /,
    **params: Any,
) -> Condition:
    passed = value is not None and _OPS[op](value, threshold)
    return Condition(feature, op, value, threshold, tolerance, passed, code, params)


def flag(
    feature: str, value: Any, passed: bool, code: str | None = None, /, **params: Any
) -> Condition:
    return Condition(feature, "is", value, None, None, passed, code, params)


def _outcome(segment: Segment, mode: Literal["all", "any"], conds: list[Condition]) -> RuleOutcome:
    fired = all(c.passed for c in conds) if mode == "all" else any(c.passed for c in conds)
    return RuleOutcome(segment, fired, mode, conds)


def _pct(x: float | None) -> int | None:
    return None if x is None else round(x * 100)


def _avg(x: float | None) -> str | None:
    return None if x is None else f"{x:.1f}"


# --------------------------------------------------------------------------- engagement
def insufficient_data(f: CustomerFeatures, cfg: SegmentationConfig) -> RuleOutcome:
    c = cfg.segments.INSUFFICIENT_DATA
    missing_critical = [x for x in c.critical_features if x in f.missing_features]
    return _outcome(Segment.INSUFFICIENT_DATA, "any", [
        compare("tenure_months", f.tenure_months, "<", c.min_tenure_months,
                c.tolerance_tenure_months, "DATA_TENURE_SHORT",
                tenure_months=f.tenure_months, min_tenure_months=c.min_tenure_months),
        compare("months_observed", f.months_observed, "<", c.min_months_observed,
                c.tolerance_months_observed, "DATA_ACTIVITY_MISSING",
                months_observed=f.months_observed, min_months_observed=c.min_months_observed),
        flag("critical_features", missing_critical, bool(missing_critical),
             "DATA_FEATURE_MISSING", features=", ".join(missing_critical)),
    ])  # fmt: skip


def dormant(f: CustomerFeatures, cfg: SegmentationConfig) -> RuleOutcome:
    c = cfg.segments.DORMANT
    last = None
    if f.days_since_last_activity is not None:
        last = (f.as_of_date - timedelta(days=f.days_since_last_activity)).isoformat()
    zero_recent = f.recent_activity_avg == 0 and f.active_plan_count >= 1
    return _outcome(Segment.DORMANT, "any", [
        compare("days_since_last_activity", f.days_since_last_activity, ">=",
                c.min_inactive_days, c.tolerance_days, "ENG_INACTIVE_DAYS",
                days=f.days_since_last_activity, threshold=c.min_inactive_days,
                last_activity=last),
        flag("recent_activity_avg", f.recent_activity_avg, zero_recent,
             "ENG_ZERO_RECENT_ACTIVITY"),
    ])  # fmt: skip


def declining(f: CustomerFeatures, cfg: SegmentationConfig) -> RuleOutcome:
    c = cfg.segments.DECLINING_ACTIVITY
    drop = None if f.activity_trend_ratio is None else round((1 - f.activity_trend_ratio) * 100)
    return _outcome(Segment.DECLINING_ACTIVITY, "all", [
        compare("prior_activity_avg", f.prior_activity_avg, ">=", c.min_prior_activity_avg,
                c.tolerance_prior_avg, "ENG_PRIOR_BASELINE",
                prior_avg=_avg(f.prior_activity_avg), min_prior_avg=c.min_prior_activity_avg),
        compare("activity_trend_ratio", f.activity_trend_ratio, "<=", c.max_trend_ratio,
                c.tolerance_trend_ratio, "ENG_ACTIVITY_DROP_PCT",
                drop_pct=drop, recent_avg=_avg(f.recent_activity_avg),
                prior_avg=_avg(f.prior_activity_avg),
                threshold_pct=round((1 - c.max_trend_ratio) * 100)),
    ])  # fmt: skip


def consistent(f: CustomerFeatures, cfg: SegmentationConfig) -> RuleOutcome:
    c = cfg.segments.CONSISTENT
    return _outcome(Segment.CONSISTENT, "all", [
        compare("active_months_last_6", f.active_months_last_6, ">=",
                c.min_active_months_last_6, c.tolerance_active_months, "ENG_ACTIVE_MONTHS",
                active_months=f.active_months_last_6, min_active_months=c.min_active_months_last_6),
        compare("activity_trend_ratio", f.activity_trend_ratio, ">", c.min_trend_ratio,
                c.tolerance_trend_ratio, "ENG_NO_MATERIAL_DECLINE",
                trend_pct=_pct(f.activity_trend_ratio)),
        compare("activity_cv_6m", f.activity_cv_6m, "<=", c.max_activity_cv, c.tolerance_cv,
                "ENG_STABLE_USAGE", cv=f.activity_cv_6m, max_cv=c.max_activity_cv),
        compare("on_time_payment_rate_12m", f.on_time_payment_rate_12m, ">=",
                c.min_on_time_rate, c.tolerance_on_time_rate, "PAY_ON_TIME_RATE",
                on_time=f.on_time_bills_last_12m, bills=f.bills_last_12m,
                rate_pct=_pct(f.on_time_payment_rate_12m), min_pct=_pct(c.min_on_time_rate)),
    ])  # fmt: skip


def standard() -> RuleOutcome:
    return RuleOutcome(
        Segment.STANDARD, True, "all", [flag("none", None, True, "ENG_NO_TARGET_PATTERN")]
    )


ENGAGEMENT_RULES = {
    EngagementSegment.INSUFFICIENT_DATA: insufficient_data,
    EngagementSegment.DORMANT: dormant,
    EngagementSegment.DECLINING_ACTIVITY: declining,
    EngagementSegment.CONSISTENT: consistent,
}


# --------------------------------------------------------------------------- qualifiers
def loyalty(
    f: CustomerFeatures, cfg: SegmentationConfig, engagement: EngagementSegment
) -> RuleOutcome:
    c = cfg.segments.LOYALTY_CANDIDATE
    return _outcome(Segment.LOYALTY_CANDIDATE, "all", [
        flag("engagement_segment", engagement.value,
             engagement == EngagementSegment.CONSISTENT),
        compare("tenure_months", f.tenure_months, ">=", c.min_tenure_months,
                c.tolerance_tenure_months, "LOY_TENURE_MONTHS",
                tenure_months=f.tenure_months, min_tenure_months=c.min_tenure_months),
        compare("on_time_payment_rate_12m", f.on_time_payment_rate_12m, ">=",
                c.min_on_time_rate, c.tolerance_on_time_rate, "PAY_ON_TIME_RATE",
                on_time=f.on_time_bills_last_12m, bills=f.bills_last_12m,
                rate_pct=_pct(f.on_time_payment_rate_12m), min_pct=_pct(c.min_on_time_rate)),
        compare("late_payments_last_6m", f.late_payments_last_6m, "<=",
                c.max_late_payments_last_6m, None, "LOY_PERFECT_RECENT_PAYMENTS"),
        compare("active_plan_count", f.active_plan_count, ">=", c.min_active_plan_count, None,
                "LOY_ACTIVE_PLAN", active_plan_count=f.active_plan_count),
    ])  # fmt: skip


def format_inr(minor: int | None) -> str | None:
    return None if minor is None else f"₹{minor / 100:,.2f}"


def payment_reminder(f: CustomerFeatures, cfg: SegmentationConfig) -> RuleOutcome:
    states = cfg.segments.PAYMENT_REMINDER.bill_states
    passed = f.current_bill_state in states
    conds = [
        flag("current_bill_state", f.current_bill_state.value, passed, "BILL_OVERDUE_DAYS",
             bill_id=f.current_bill_id, days_overdue=f.days_overdue),
    ]  # fmt: skip
    if passed and f.current_bill_state == BillState.PARTIALLY_PAID_OVERDUE:
        conds.append(flag("outstanding_minor", f.outstanding_minor, True, "BILL_PARTIAL_PAYMENT",
                          bill_id=f.current_bill_id,
                          outstanding=format_inr(f.outstanding_minor)))  # fmt: skip
    return _outcome(Segment.PAYMENT_REMINDER, "all", conds)


def billing_info(f: CustomerFeatures) -> list[Condition]:
    """Informational codes that force escalation downstream; they never set a segment."""
    if f.current_bill_state == BillState.DISPUTED:
        return [flag("current_bill_state", "DISPUTED", True, "BILL_DISPUTED",
                     bill_id=f.current_bill_id)]  # fmt: skip
    if f.current_bill_state == BillState.DATA_CONFLICT:
        conflict = f.bill_conflict_type.value if f.bill_conflict_type else "UNKNOWN"
        return [flag("current_bill_state", "DATA_CONFLICT", True, "BILL_DATA_CONFLICT",
                     bill_id=f.current_bill_id, conflict_type=conflict)]  # fmt: skip
    return []
