"""LLMInput, LLMDraftOutput, RawDraft, RenderedDraft.

Owner: SHARED (LLMInput built by M2, the rest produced by M3). Drafted by M4 for CP0 from
blueprint sections 8.4-8.5; needs approval.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import Objective
Owner: SHARED — all owners must approve changes (CLAUDE.md §12.1).

This first version adds ``LLMInput`` (§8.4): built by M2 (``app/policy/llm_input.py``),
consumed by M3 (``MessageGenerator``). M3 adds ``LLMDraftOutput``, ``RawDraft`` and
``RenderedDraft`` in a follow-up PR.

Privacy rule: ``LLMInput`` must never carry the email address, customer_id, consent
flags, payment history or raw activity numbers.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import Objective
from app.schemas.policy import VerifiedOffer


class ToneSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    rules: list[str] = []


class LLMInput(BaseModel):
    """Minimal verified input; the only data the generation layer ever sees.

    Must never contain email, customer_id, consent flags or payment history.
    """
    rules: list[str] = Field(default_factory=list)


class LLMInput(BaseModel):
    """The minimal, verified context the LLM may see (§8.4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    first_name: str
    objective: Objective
    segment_summary: str
    tone: ToneSpec
    allowed_slots: dict[str, str]
    offer: dict[str, str] | None = None
    required_disclaimers: list[str] = []
    template_skeleton: str = ""
    forbidden: list[str] = []


class LLMDraftOutput(BaseModel):
    """Structured JSON the LLM must return (validated before use)."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=5, max_length=90)
    body: str = Field(min_length=40, max_length=1500)
    customer_segment: str
    communication_objective: str
    facts_used: list[str]
    offer_id: str | None = None
    disclaimer_keys: list[str] = []


class GenerationMeta(BaseModel):
    """Provenance recorded for FR-09."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_provider: str  # e.g. "google", "template-only"
    model_id: str
    prompt_version: str | None = None  # None when template-only
    template_id: str
    template_version: str
    fallback_used: bool = False
    fallback_reason: str | None = None
    llm_latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class RawDraft(BaseModel):
    """Generator output; body may still contain {{slot}} tokens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str
    body: str
    facts_used: list[str] = []
    offer_id: str | None = None
    disclaimer_keys: list[str] = []
    meta: GenerationMeta


class RenderedDraft(BaseModel):
    """Slots replaced by verified values and disclaimer text appended by code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str
    body: str
    facts_used: dict[str, str] = {}
    offer_id: str | None = None
    disclaimer_keys: list[str] = []
    meta: GenerationMeta
    #: slot name -> verified display value; the LLM writes ``{{slot}}``, code fills it.
    allowed_slots: dict[str, str]
    offer: VerifiedOffer | None = None
    required_disclaimers: list[str] = Field(default_factory=list)
    template_skeleton: str
    forbidden: list[str] = Field(default_factory=list)
