"""GuardrailCheck protocol, guardrail config, and the verified-facts allow-list.

Owner: M3.

Open/Closed (§3.2): adding a check = one new file in ``checks/`` + one line in
``registry.py``. The runner never changes.

A check returns:
- ``[]``             -> passed (runner records one PASS finding),
- ``[Finding, ...]`` -> failed,
- ``None``           -> not evaluated (needed context absent; listed in checks_skipped).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.generation.clients.template_only import verified_slot_values
from app.generation.content import SLOT_RE, DisclaimerStore, content_version, load_yaml
from app.guardrails import extractors as ex
from app.schemas.enums import Severity
from app.schemas.generation import RenderedDraft
from app.schemas.validation import Finding, ValidationContext
from config.settings import POLICIES_DIR

Field_ = Literal["subject", "body"]


class GuardrailCheck(Protocol):
    check_id: str
    mandatory: bool

    def run(
        self, draft: RenderedDraft, ctx: ValidationContext, facts: VerifiedFacts
    ) -> list[Finding] | None: ...


# --------------------------------------------------------------------------- config


class GuardrailConfig(BaseModel):
    """Parsed blocked_language.yaml (validated at startup)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    always_blocked: dict[str, list[str]]
    pressure_terms_warn_in: list[str]
    pressure_terms: list[str]
    casual_terms_warn_in: list[str]
    casual_terms: list[str]
    contradiction: dict[Literal["billing_reminder_forbids", "non_billing_forbids"], list[str]]
    offer_keywords: list[str]
    offer_keyword_exceptions: list[str] = []
    internal_code_prefixes: list[str]
    internal_terms: list[str]

    @property
    def blocked_terms(self) -> list[tuple[str, str]]:
        """(category, term) pairs."""
        return [(cat, t) for cat, terms in self.always_blocked.items() for t in terms]


@dataclass(frozen=True)
class GuardrailResources:
    config: GuardrailConfig
    disclaimers: DisclaimerStore
    version: str


def load_resources(
    blocked_path: Path = POLICIES_DIR / "blocked_language.yaml",
    disclaimers: DisclaimerStore | None = None,
) -> GuardrailResources:
    data, text = load_yaml(blocked_path)
    cfg = GuardrailConfig.model_validate(data)
    disc = disclaimers or DisclaimerStore()
    return GuardrailResources(
        config=cfg,
        disclaimers=disc,
        version=f"{cfg.version}+{content_version(text)}|{disc.version}",
    )


# --------------------------------------------------------------------------- verified facts


class VerifiedFacts:
    """Allow-list of facts derived ONLY from LLMInput (+ approved disclaimer text)."""

    def __init__(self, ctx: ValidationContext, disclaimers: DisclaimerStore) -> None:
        self.slots: dict[str, str] = verified_slot_values(ctx.llm_input)
        filled_disclaimers = []
        for key in ctx.llm_input.required_disclaimers:
            if key in disclaimers.texts:
                filled_disclaimers.append(self.fill(disclaimers.text(key)))
        self.disclaimer_texts: list[str] = filled_disclaimers
        self.values: list[str] = list(self.slots.values()) + filled_disclaimers

    def fill(self, text: str) -> str:
        return SLOT_RE.sub(lambda m: self.slots.get(m.group(1), m.group(0)), text)

    @cached_property
    def _joined_lower(self) -> str:
        return "\n".join(ex.normalize_ws(v) for v in self.values)

    def contains_text(self, span_text: str) -> bool:
        """True if the span appears verbatim (case/space-insensitive) in a verified value."""
        return ex.normalize_ws(span_text) in self._joined_lower

    @cached_property
    def money(self) -> set[Decimal]:
        return {s.value for v in self.values for s in ex.find_money(v)}

    @cached_property
    def dates(self) -> list[ex.DateValue]:
        return [
            s.value
            for v in self.values
            for s in ex.find_dates(v)
            if isinstance(s.value, ex.DateValue)
        ]

    @cached_property
    def unit_numbers(self) -> set[tuple[Decimal, str]]:
        return {s.value for v in self.values for s in ex.find_unit_numbers(v)}

    @cached_property
    def bare_numbers(self) -> set[Decimal]:
        return {n for v in self.slots.values() if (n := ex.bare_number(v)) is not None}


# --------------------------------------------------------------------------- helpers


def fields(draft: RenderedDraft) -> list[tuple[Field_, str]]:
    return [("subject", draft.subject), ("body", draft.body)]


def finding(
    check: GuardrailCheck,
    message: str,
    field: Field_ | None = None,
    span: ex.Span | None = None,
    severity: Severity | None = None,
) -> Finding:
    if severity is None:
        severity = Severity.BLOCK if check.mandatory else Severity.WARN
    return Finding(
        check_id=check.check_id,
        severity=severity,
        mandatory=check.mandatory,
        message=message,
        field=field,
        span=span.text if span else None,
        start=span.start if span else None,
        end=span.end if span else None,
    )
