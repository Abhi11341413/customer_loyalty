"""Transparent rule-confidence score (NOT a calibrated probability).

Owner: M1.

    confidence   = completeness x margin
    completeness = 1 - missing relevant features / relevant features
    margin       = mean over supporting conditions of min(1, |value - threshold| / tolerance)
                   (categorical conditions count as 1)
    band         = HIGH >= 0.75, MEDIUM >= 0.45, else LOW   (from segments.yaml)

Special cases:
- STANDARD has no supporting conditions, so its margin is how clearly the customer misses each
  targeted segment (mean over DORMANT / DECLINING / CONSISTENT of their clearest failure).
- INSUFFICIENT_DATA measures completeness over all core activity/payment features, so it is
  low by design: any downstream decision would rest on thin evidence.
"""

from statistics import mean

from app.schemas.customer import CustomerFeatures
from app.schemas.enums import ConfidenceBand, Segment
from app.segmentation.config import ConfidenceCfg
from app.segmentation.rules import Condition, RuleOutcome

CORE_FEATURES = [
    "recent_activity_avg",
    "prior_activity_avg",
    "activity_trend_ratio",
    "activity_cv_6m",
    "days_since_last_activity",
    "on_time_payment_rate_12m",
]


def condition_margin(c: Condition) -> float:
    """Distance from the threshold in tolerance units, capped at 1 (categorical = 1)."""
    if c.value is None:
        return 0.0
    if c.tolerance is None:
        return 1.0
    if c.tolerance <= 0:
        return 1.0
    return min(1.0, abs(float(c.value) - float(c.threshold)) / c.tolerance)


def failure_margin(rule: RuleOutcome) -> float:
    """How clearly a rule did NOT fire."""
    failing = [condition_margin(c) for c in rule.conditions if not c.passed]
    if not failing:
        return 0.0
    # 'all' rule: one clear failure suffices; 'any' rule: every condition must fail.
    return max(failing) if rule.mode == "all" else min(failing)


def band(score: float, cfg: ConfidenceCfg) -> ConfidenceBand:
    if score >= cfg.high:
        return ConfidenceBand.HIGH
    if score >= cfg.medium:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


def score(
    features: CustomerFeatures,
    engagement_rule: RuleOutcome,
    evaluated: list[RuleOutcome],
    fired_flags: list[RuleOutcome],
) -> float:
    """`evaluated` = engagement rules checked before (and including) the winning one."""
    if engagement_rule.segment == Segment.INSUFFICIENT_DATA:
        relevant = set(CORE_FEATURES)
    else:
        relevant = set().union(*(r.features for r in evaluated + fired_flags)) & (
            set(CustomerFeatures.model_fields)
        )
    missing = relevant & set(features.missing_features)
    completeness = 1 - len(missing) / len(relevant) if relevant else 1.0

    if engagement_rule.segment == Segment.STANDARD:
        others = [r for r in evaluated if r.segment != Segment.STANDARD and not r.fired]
        margins = [failure_margin(r) for r in others if r.segment != Segment.INSUFFICIENT_DATA]
    else:
        margins = [condition_margin(c) for c in engagement_rule.supporting]
    for r in fired_flags:
        margins += [condition_margin(c) for c in r.supporting]
    margin = mean(margins) if margins else 1.0
    return round(max(0.0, min(1.0, completeness * margin)), 3)
