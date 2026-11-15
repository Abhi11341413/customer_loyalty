"""ClassificationResult, ReasonCode.

Owner: SHARED (produced by M1). Drafted by M4 for CP0 from blueprint sections 5.1-5.4;
needs approval.
"""

from __future__ import annotations

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
    agrees: bool


class ClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

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
