"""Hosted LLM providers over plain HTTP (httpx) — no vendor SDK dependency.

Owner: M3.

The team has not chosen a provider yet (OPEN-1), so these use the public REST APIs
via httpx (already a dependency, §17). Model IDs always come from settings; nothing
here hard-codes a model name. Keys are passed in headers, never in URLs or logs.

These clients are exercised only by ``@pytest.mark.live`` tests (need a real key).
"""

from __future__ import annotations

import time

import httpx

from app.generation.clients.base import (
    LLMInvalidOutputError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMResponse,
    LLMTimeoutError,
    LLMUnavailableError,
)

TEMPERATURE = 0.4  # §8.1: 0.3-0.5
MAX_OUTPUT_TOKENS = 600


def _retry_after(resp: httpx.Response) -> float | None:
    value = resp.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _post(url: str, headers: dict, payload: dict, timeout_s: float) -> tuple[dict, int]:
    """POST JSON and map transport/HTTP failures to typed LLM errors."""
    start = time.perf_counter()
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=timeout_s)
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError(str(exc) or "timeout") from exc
    except httpx.HTTPError as exc:
        raise LLMUnavailableError(type(exc).__name__) from exc
    latency_ms = int((time.perf_counter() - start) * 1000)
    if resp.status_code == 429:
        raise LLMRateLimitError("HTTP 429", retry_after_s=_retry_after(resp))
    if resp.status_code >= 400:
        # Body may echo the request; keep only the status in the error.
        raise LLMUnavailableError(f"HTTP {resp.status_code}")
    try:
        return resp.json(), latency_ms
    except ValueError as exc:
        raise LLMInvalidOutputError("provider returned non-JSON envelope") from exc


class GeminiClient:
    provider = "gemini"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model_id: str) -> None:
        if not api_key or not model_id:
            raise LLMUnavailableError("gemini: GEMINI_API_KEY and LLM_MODEL_ID are required")
        self._key = api_key
        self.model_id = model_id

    def complete_json(self, system: str, user: str, schema: dict, timeout_s: float) -> LLMResponse:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": TEMPERATURE,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
            },
        }
        data, latency_ms = _post(
            f"{self.BASE_URL}/{self.model_id}:generateContent",
            {"x-goog-api-key": self._key, "content-type": "application/json"},
            payload,
            timeout_s,
        )
        if data.get("promptFeedback", {}).get("blockReason"):
            raise LLMRefusalError("gemini: prompt blocked")
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMInvalidOutputError("gemini: no candidates")
        cand = candidates[0]
        if cand.get("finishReason") in {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"}:
            raise LLMRefusalError(f"gemini: finishReason {cand.get('finishReason')}")
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise LLMInvalidOutputError("gemini: empty text")
        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            text=text,
            provider=self.provider,
            model_id=self.model_id,
            latency_ms=latency_ms,
            prompt_tokens=usage.get("promptTokenCount"),
            completion_tokens=usage.get("candidatesTokenCount"),
        )


class AnthropicClient:
    provider = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(self, api_key: str, model_id: str) -> None:
        if not api_key or not model_id:
            raise LLMUnavailableError("anthropic: ANTHROPIC_API_KEY and LLM_MODEL_ID are required")
        self._key = api_key
        self.model_id = model_id

    def complete_json(self, system: str, user: str, schema: dict, timeout_s: float) -> LLMResponse:
        payload = {
            "model": self.model_id,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": TEMPERATURE,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        data, latency_ms = _post(
            self.URL,
            {
                "x-api-key": self._key,
                "anthropic-version": self.API_VERSION,
                "content-type": "application/json",
            },
            payload,
            timeout_s,
        )
        if data.get("stop_reason") == "refusal":
            raise LLMRefusalError("anthropic: refusal")
        text = "".join(
            b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text"
        ).strip()
        if not text:
            raise LLMInvalidOutputError("anthropic: empty text")
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            provider=self.provider,
            model_id=self.model_id,
            latency_ms=latency_ms,
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
        )
