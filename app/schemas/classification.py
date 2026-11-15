"""Classification contracts: ReasonCode and ClassificationResult (FR-02).

Owner: SHARED (produced by M1). Changes need approval from all affected owners.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import ConfidenceBand, EngagementSegment, Segment


class ReasonCode(BaseModel):
    """One explainable reason. `text` comes from a fixed template, never from the LLM."""

    model_config = ConfigDict(frozen=True)

    code: str
    segment: Segment | None = None
    params: dict[str, Any] = {}
    text: str


class ShadowPrediction(BaseModel):
    """Optional advisory model output. Never overrides the rules."""

    label: str
    proba: float
    agrees: bool


class ClassificationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    customer_id: str
    as_of_date: date
    engagement_segment: EngagementSegment
    segments: list[Segment]
    primary_segment: Segment
    reason_codes: list[ReasonCode]
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_band: ConfidenceBand
    missing_features: list[str] = []
    ruleset_version: str
    classification_id: str | None = None
    shadow: ShadowPrediction | None = None


class ClassifyRequest(BaseModel):
    as_of_date: date | None = None
