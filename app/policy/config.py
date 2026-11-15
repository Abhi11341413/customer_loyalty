"""Typed, validated policy configuration for M2 (billing / contact / strategy YAMLs).

Owner: M2.

A typo in a YAML file fails loudly at load time (D7) instead of silently changing
behaviour. Each config carries a ``version_tag`` like ``billing.yaml@1.0#3f9a1c2``
(declared version + content hash) for the audit trail (FR-09).

M4's ``app/core/policy_loader.py`` may later wrap these loaders; the models stay here.
"""

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.enums import (
    BILLING_REMINDER_OBJECTIVES,
    NON_DRAFT_OBJECTIVES,
    MessageCategory,
    Objective,
    OfferType,
    Segment,
)

POLICY_DIR = Path(__file__).resolve().parents[2] / "config" / "policies"

_CFG = ConfigDict(extra="forbid", frozen=True)


class PolicyConfigError(ValueError):
    """A policy YAML file is missing or invalid."""


# --------------------------------------------------------------------------- billing


class ReminderStage(BaseModel):
    model_config = _CFG

    stage: int = Field(ge=1)
    name: str
    min_days_overdue: int = Field(ge=1)
    max_days_overdue: int
    tone: str
    template_id: str


class BillingConfig(BaseModel):
    model_config = _CFG

    version: str
    currency: str = "INR"
    grace_days: int = Field(default=0, ge=0)
    reminder_stages: list[ReminderStage]
    beyond_max_stage: Literal["ESCALATE"] = "ESCALATE"
    min_days_between_reminders: int = Field(ge=0)
    no_stage_skipping: bool = True
    bill_lookback_months: int = Field(default=3, ge=1)
    support_path: str = Field(min_length=10)
    version_tag: str = ""

    @model_validator(mode="after")
    def _stages_contiguous(self) -> "BillingConfig":
        stages = sorted(self.reminder_stages, key=lambda s: s.stage)
        if not stages:
            raise ValueError("reminder_stages must not be empty")
        expected_min = stages[0].min_days_overdue
        for i, s in enumerate(stages, start=1):
            if s.stage != i:
                raise ValueError("reminder stages must be numbered 1..n")
            if s.max_days_overdue < s.min_days_overdue:
                raise ValueError(f"stage {s.stage}: max_days_overdue < min_days_overdue")
            if s.min_days_overdue != expected_min:
                raise ValueError(f"stage {s.stage}: day ranges must be contiguous")
            expected_min = s.max_days_overdue + 1
        return self

    @property
    def max_stage(self) -> int:
        return len(self.reminder_stages)

    def stage_for(self, days_overdue: int) -> int | None:
        """Stage for a number of days overdue; ``None`` if outside every stage."""
        for s in self.reminder_stages:
            if s.min_days_overdue <= days_overdue <= s.max_days_overdue:
                return s.stage
        return None

    def stage_config(self, stage: int) -> ReminderStage:
        return next(s for s in self.reminder_stages if s.stage == stage)


# --------------------------------------------------------------------------- contact

_PREFERENCE_FLAGS = {"email_service_consent", "email_marketing_consent"}
GlobalBlocker = Literal[
    "email_opt_out", "account_closed", "do_not_contact_until_active", "preferred_channel_none"
]


class FrequencyCaps(BaseModel):
    model_config = _CFG

    marketing_min_days_between: int = Field(ge=0)
    total_max_per_30_days: int = Field(ge=1)


class DuplicateWindows(BaseModel):
    model_config = _CFG

    same_objective: int = Field(ge=0)
    same_offer: int = Field(ge=0)


class ContactConfig(BaseModel):
    model_config = _CFG

    version: str
    marketing_requires: list[str]
    service_requires: list[str]
    global_blockers: list[GlobalBlocker]
    frequency_caps: FrequencyCaps
    duplicate_window_days: DuplicateWindows
    version_tag: str = ""

    @model_validator(mode="after")
    def _known_flags(self) -> "ContactConfig":
        unknown = set(self.marketing_requires + self.service_requires) - _PREFERENCE_FLAGS
        if unknown:
            raise ValueError(f"unknown consent flags: {sorted(unknown)}")
        return self

    def required_flags(self, category: MessageCategory) -> list[str]:
        if category is MessageCategory.MARKETING:
            return self.marketing_requires
        return self.service_requires


# --------------------------------------------------------------------------- strategy


class ObjectiveConfig(BaseModel):
    model_config = _CFG

    category: MessageCategory
    template_id: str
    template_version: str
    tone: str
    allowed_offer_types: list[OfferType] = Field(default_factory=list)
    offer_required: bool = False
    fallback_objective: Objective | None = None
    disclaimers: list[str] = Field(default_factory=list)
    offer_disclaimers: list[str] = Field(default_factory=list)
    cta_key: str
    summary: str
    skeleton: str


class EngagementRule(BaseModel):
    model_config = _CFG

    when_all: list[Segment] = Field(min_length=1)
    objective: Objective


class CtaConfig(BaseModel):
    model_config = _CFG

    slot: str
    text: str


class StrategyConfig(BaseModel):
    model_config = _CFG

    version: str
    escalate_segments: list[Segment] = Field(default_factory=list)
    billing_stage_objectives: dict[int, Objective]
    engagement_rules: list[EngagementRule]
    objectives: dict[Objective, ObjectiveConfig]
    ctas: dict[str, CtaConfig]
    forbidden: list[str] = Field(default_factory=list)
    version_tag: str = ""

    @model_validator(mode="after")
    def _references_resolve(self) -> "StrategyConfig":
        for obj in self.objectives:
            if obj in NON_DRAFT_OBJECTIVES:
                raise ValueError(f"{obj} must not have an objective config")
        referenced = [r.objective for r in self.engagement_rules]
        referenced += list(self.billing_stage_objectives.values())
        referenced += [
            o.fallback_objective for o in self.objectives.values() if o.fallback_objective
        ]
        missing = {o for o in referenced if o not in self.objectives}
        if missing:
            raise ValueError(f"objectives referenced but not configured: {sorted(missing)}")
        for stage_obj in self.billing_stage_objectives.values():
            if stage_obj not in BILLING_REMINDER_OBJECTIVES:
                raise ValueError(f"{stage_obj} is not a billing reminder objective")
        for name, o in self.objectives.items():
            if o.cta_key not in self.ctas:
                raise ValueError(f"{name}: unknown cta_key {o.cta_key!r}")
            if o.offer_required and o.fallback_objective is None:
                raise ValueError(f"{name}: offer_required needs a fallback_objective")
        return self


# --------------------------------------------------------------------------- loading


def _load(name: str, model: type[BaseModel], policy_dir: Path) -> BaseModel:
    path = policy_dir / name
    try:
        raw_bytes = path.read_bytes()
    except FileNotFoundError as exc:
        raise PolicyConfigError(f"policy file not found: {path}") from exc
    data = yaml.safe_load(raw_bytes) or {}
    if not isinstance(data, dict):
        raise PolicyConfigError(f"{name}: top level must be a mapping")
    # Normalise line endings so the tag is identical on Windows (CRLF) and Linux/macOS (LF).
    digest = hashlib.sha256(raw_bytes.replace(b"\r\n", b"\n")).hexdigest()[:7]
    data["version_tag"] = f"{name}@{data.get('version', '?')}#{digest}"
    try:
        return model.model_validate(data)
    except ValueError as exc:
        raise PolicyConfigError(f"{name} is invalid: {exc}") from exc


@lru_cache
def load_billing_config(policy_dir: Path = POLICY_DIR) -> BillingConfig:
    return _load("billing.yaml", BillingConfig, policy_dir)  # type: ignore[return-value]


@lru_cache
def load_contact_config(policy_dir: Path = POLICY_DIR) -> ContactConfig:
    return _load("contact.yaml", ContactConfig, policy_dir)  # type: ignore[return-value]


@lru_cache
def load_strategy_config(policy_dir: Path = POLICY_DIR) -> StrategyConfig:
    return _load("strategy.yaml", StrategyConfig, policy_dir)  # type: ignore[return-value]
