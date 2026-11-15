"""LLMInput, LLMDraftOutput, RawDraft, RenderedDraft.

Owner: SHARED — all owners must approve changes (CLAUDE.md §12.1).

- ``LLMInput`` (§8.4): built by M2 (``app/policy/llm_input.py``), consumed by M3.
- ``LLMDraftOutput`` (§8.5): the JSON shape the LLM must return (M3).
- ``RawDraft``: generator output, body still contains ``{{slots}}`` (M3).
- ``RenderedDraft``: slots replaced by verified values + disclaimers appended (M3).
  This is what guardrails validate and what the reviewer sees and edits.

Privacy rule: ``LLMInput`` must never carry the email address, customer_id, consent
flags, payment history or raw activity numbers.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import Objective
from app.schemas.policy import VerifiedOffer

#: Subject sentinel the LLM returns when INPUT is insufficient (system prompt rule 6).
INSUFFICIENT_INPUT_SENTINEL = "INSUFFICIENT_INPUT"


class ToneSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    rules: list[str] = Field(default_factory=list)


class LLMInput(BaseModel):
    """The minimal, verified context the LLM may see (§8.4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    first_name: str
    objective: Objective
    segment_summary: str
    tone: ToneSpec
    #: slot name -> verified display value; the LLM writes ``{{slot}}``, code fills it.
    allowed_slots: dict[str, str]
    offer: VerifiedOffer | None = None
    required_disclaimers: list[str] = Field(default_factory=list)
    template_skeleton: str
    forbidden: list[str] = Field(default_factory=list)


class LLMDraftOutput(BaseModel):
    """Structured output the LLM must return (§8.5). Extra keys are ignored."""

    model_config = ConfigDict(extra="ignore")

    subject: str = Field(min_length=5, max_length=90)
    body: str = Field(min_length=40, max_length=1500)  # may contain {{slots}}
    customer_segment: str = ""
    communication_objective: str  # must echo LLMInput.objective
    facts_used: list[str] = Field(default_factory=list)  # slot names
    offer_id: str | None = None  # must equal input offer id or null
    disclaimer_keys: list[str] = Field(default_factory=list)


class FallbackEvent(BaseModel):
    """One provider attempt that failed and caused a fallback (audited as LLM_FALLBACK)."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model_id: str
    error_type: str  # e.g. LLMTimeoutError, LLMInvalidOutputError, INSUFFICIENT_INPUT
    detail: str = ""


class RawDraft(BaseModel):
    """Generator output before slot filling. Body/subject may contain ``{{slots}}``."""

    model_config = ConfigDict(frozen=True)

    subject: str
    body: str
    objective: Objective
    offer_id: str | None = None
    facts_used: list[str] = Field(default_factory=list)
    disclaimer_keys: list[str] = Field(default_factory=list)
    communication_objective: str  # echoed by the LLM (or set by template)

    template_id: str
    template_version: str
    prompt_version: str | None = None  # None when template-only
    model_provider: str  # e.g. "gemini", "anthropic", "template"
    model_id: str  # "template-only" for the fallback

    fallback_events: list[FallbackEvent] = Field(default_factory=list)
    llm_attempts: int = 0
    llm_latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    @property
    def is_template_only(self) -> bool:
        return self.model_provider == "template"


class RenderedDraft(BaseModel):
    """Customer-facing text: verified values filled in, disclaimers appended (§8.3)."""

    model_config = ConfigDict(frozen=True)

    subject: str
    body: str
    raw: RawDraft
    #: slot name -> verified value actually substituted (grounding evidence, FR-09).
    facts_used: dict[str, str] = Field(default_factory=dict)
    #: slots referenced in the text that were not in the verified set (-> BLOCK).
    unknown_slots: list[str] = Field(default_factory=list)
    disclaimer_keys_appended: list[str] = Field(default_factory=list)
    content_hash: str  # "sha256:<hex>" of subject + "\n" + body; approval binds to it
    edited: bool = False  # True once a reviewer has changed the text
