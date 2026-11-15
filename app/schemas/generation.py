"""LLMInput, LLMDraftOutput, RawDraft, RenderedDraft.

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
