"""SegmentationEngine: CustomerFeatures -> ClassificationResult (pure, deterministic).

Owner: M1. Knows nothing about offers, templates or the LLM.

Two axes + one qualifier:
- engagement: exactly one of INSUFFICIENT_DATA > DORMANT > DECLINING_ACTIVITY > CONSISTENT >
  STANDARD (first match in `engagement_order` wins)
- LOYALTY_CANDIDATE qualifier: only when engagement is CONSISTENT
- PAYMENT_REMINDER flag: independent (bill OVERDUE / PARTIALLY_PAID_OVERDUE)
DISPUTED / DATA_CONFLICT bills never set PAYMENT_REMINDER; they add BILL_DISPUTED /
BILL_DATA_CONFLICT reason codes so the strategy escalates.
"""

from dataclasses import dataclass

from app.schemas.classification import ClassificationResult
from app.schemas.customer import CustomerFeatures
from app.schemas.enums import EngagementSegment, Segment
from app.segmentation import confidence, rules
from app.segmentation.config import SegmentationConfig, default_config
from app.segmentation.reasons import ReasonCodeBuilder


@dataclass(frozen=True)
class ClassificationTrace:
    """Full rule trace — useful for debugging, tests and the reviewer UI."""

    evaluated: list[rules.RuleOutcome]
    engagement_rule: rules.RuleOutcome
    flags: list[rules.RuleOutcome]


class SegmentationEngine:
    def __init__(self, config: SegmentationConfig | None = None) -> None:
        self.config = config or default_config()
        self._reasons = ReasonCodeBuilder(self.config.reason_texts)

    def trace(self, f: CustomerFeatures) -> ClassificationTrace:
        evaluated: list[rules.RuleOutcome] = []
        winner: rules.RuleOutcome | None = None
        for seg in self.config.engagement_order:
            outcome = (
                rules.standard() if seg == EngagementSegment.STANDARD
                else rules.ENGAGEMENT_RULES[seg](f, self.config)
            )  # fmt: skip
            evaluated.append(outcome)
            if outcome.fired:
                winner = outcome
                break
        if winner is None:  # STANDARD missing from engagement_order: still never unclassified
            winner = rules.standard()
            evaluated.append(winner)
        engagement = EngagementSegment(winner.segment.value)
        flags = [rules.loyalty(f, self.config, engagement), rules.payment_reminder(f, self.config)]
        return ClassificationTrace(evaluated, winner, flags)

    def classify(self, f: CustomerFeatures) -> ClassificationResult:
        t = self.trace(f)
        fired_flags = [r for r in t.flags if r.fired]
        segments = [t.engagement_rule.segment] + [r.segment for r in fired_flags]
        primary = next(
            (s for s in self.config.primary_precedence if s in segments), t.engagement_rule.segment
        )
        score = confidence.score(f, t.engagement_rule, t.evaluated, fired_flags)
        return ClassificationResult(
            customer_id=f.customer_id,
            as_of_date=f.as_of_date,
            engagement_segment=EngagementSegment(t.engagement_rule.segment.value),
            segments=segments,
            primary_segment=Segment(primary),
            reason_codes=self._reasons.build(
                [t.engagement_rule, *fired_flags], rules.billing_info(f)
            ),
            confidence=score,
            confidence_band=confidence.band(score, self.config.confidence),
            missing_features=list(f.missing_features),
            ruleset_version=self.config.ruleset_version,
        )
