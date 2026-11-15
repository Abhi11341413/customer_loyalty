"""Build the provider chain from settings + a simple in-process rate limiter (§8.2).

Owner: M3.

Chain = primary -> optional fallback provider -> (TemplateOnly, added by the generator).
A provider that cannot be constructed (e.g. no API key) is skipped with a warning, so
the app starts in template mode instead of failing (§8.2 "No API key configured").
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable

from app.generation.clients.base import LLMClient, LLMError, LLMRateLimitError, LLMResponse
from app.generation.clients.fake import FakeAdversarialClient
from app.generation.clients.http_providers import AnthropicClient, GeminiClient
from config.settings import Settings

log = logging.getLogger(__name__)

NO_LLM_PROVIDERS = {"template", "", "none"}


class RateLimitedClient:
    """Wraps a client with a sliding-window limit of ``max_rpm`` calls per minute.

    Over the limit it raises ``LLMRateLimitError`` immediately (never blocks the
    request); the generator then falls back down the chain.
    """

    def __init__(
        self, inner: LLMClient, max_rpm: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._inner = inner
        self._max = max(1, max_rpm)
        self._clock = clock
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()
        self.provider = inner.provider
        self.model_id = inner.model_id

    def complete_json(self, system: str, user: str, schema: dict, timeout_s: float) -> LLMResponse:
        now = self._clock()
        with self._lock:
            while self._calls and now - self._calls[0] >= 60:
                self._calls.popleft()
            if len(self._calls) >= self._max:
                raise LLMRateLimitError("local rate limit (LLM_MAX_RPM)", retry_after_s=None)
            self._calls.append(now)
        return self._inner.complete_json(system, user, schema, timeout_s)


def _secret(value) -> str:
    return value.get_secret_value() if value is not None else ""


def make_client(provider: str, settings: Settings) -> LLMClient | None:
    """Construct one provider client, or None for template mode / unusable config."""
    provider = (provider or "").strip().lower()
    if provider in NO_LLM_PROVIDERS:
        return None
    try:
        if provider == "gemini":
            return GeminiClient(_secret(settings.gemini_api_key), settings.llm_model_id)
        if provider == "anthropic":
            return AnthropicClient(_secret(settings.anthropic_api_key), settings.llm_model_id)
        if provider == "fake_adversarial":
            return FakeAdversarialClient()
    except LLMError as exc:
        log.warning("LLM provider %s disabled: %s", provider, exc)
        return None
    log.warning("LLM provider %s is not implemented; using template mode", provider)
    return None


def build_chain(settings: Settings) -> list[LLMClient]:
    """Hosted clients in fallback order (may be empty = template-only mode)."""
    chain: list[LLMClient] = []
    for name in (settings.llm_provider, settings.llm_fallback_provider):
        client = make_client(name, settings)
        if client is not None and all(c.provider != client.provider for c in chain):
            chain.append(RateLimitedClient(client, settings.llm_max_rpm))
    return chain


def llm_mode(chain: list[LLMClient]) -> str:
    """For the health endpoint / UI banner."""
    return chain[0].provider if chain else "template"
