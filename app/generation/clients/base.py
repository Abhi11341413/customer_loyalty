"""LLMClient protocol + typed errors (LSP contract, §3.3).

Owner: M3.

Every implementation, given a system prompt, user prompt and JSON schema, either
returns an ``LLMResponse`` or raises one of the ``LLMError`` subclasses below. It must
never return ``None``, raise a vendor-specific exception, or return another shape.
Only modules in ``app/generation/clients/`` may talk to provider APIs (§11.6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class LLMError(Exception):
    """Base class for every provider failure the generator knows how to handle."""


class LLMTimeoutError(LLMError):
    pass


class LLMRateLimitError(LLMError):
    def __init__(self, message: str = "rate limited", retry_after_s: float | None = None):
        super().__init__(message)
        self.retry_after_s = retry_after_s


class LLMUnavailableError(LLMError):
    """5xx, network error, missing key, bad request/config."""


class LLMInvalidOutputError(LLMError):
    """Response is empty, not JSON, or fails the output schema."""


class LLMRefusalError(LLMError):
    """Provider-side safety refusal."""


@dataclass(frozen=True)
class LLMResponse:
    text: str  # raw text returned by the model (expected to be JSON)
    provider: str
    model_id: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@runtime_checkable
class LLMClient(Protocol):
    provider: str
    model_id: str

    def complete_json(
        self, system: str, user: str, schema: dict, timeout_s: float
    ) -> LLMResponse: ...
