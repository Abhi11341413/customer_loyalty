"""Classification contracts: ReasonCode and ClassificationResult (FR-02).

Owner: SHARED (produced by M1). Drafted by M4 for CP0 from blueprint sections 5.1-5.4;
needs approval.
"""

from __future__ import annotations

Owner: SHARED (produced by M1). Changes need approval from all affected owners.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import ConfidenceBand, EngagementSegment, Segment


class ReasonCode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    segment: str | None = None
    params: dict[str, Any] = {}
    text: str  # from a fixed template per code (reason_codes.yaml), never from the LLM


class ShadowResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    proba: float = Field(ge=0, le=1)
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
    model_config = ConfigDict(extra="forbid", frozen=True)
    model_config = ConfigDict(frozen=True)

    customer_id: str
    as_of_date: date
    engagement_segment: EngagementSegment
    segments: list[Segment]
    primary_segment: Segment
    reason_codes: list[ReasonCode] = []
    confidence: float = Field(ge=0, le=1)
    confidence_band: ConfidenceBand
    missing_features: list[str] = []
    ruleset_version: str
    shadow: ShadowResult | None = None
    reason_codes: list[ReasonCode]
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_band: ConfidenceBand
    missing_features: list[str] = []
    ruleset_version: str
    classification_id: str | None = None
    shadow: ShadowPrediction | None = None


class ClassifyRequest(BaseModel):
    as_of_date: date | None = None
