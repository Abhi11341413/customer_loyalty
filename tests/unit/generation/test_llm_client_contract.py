"""LLMClient contract (LSP, §3.3): return LLMResponse or raise a typed LLMError.

HTTP providers are tested against a mocked httpx.post — no network, no key.
Real calls are only in the `live` test at the bottom.
"""

import os

import httpx
import pytest

from app.generation.clients import http_providers
from app.generation.clients.base import (
    LLMClient,
    LLMError,
    LLMInvalidOutputError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMResponse,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.generation.clients.chain import RateLimitedClient, build_chain, llm_mode
from app.generation.clients.fake import FakeAdversarialClient, FakeLLMClient
from app.generation.clients.http_providers import AnthropicClient, GeminiClient
from config.settings import Settings


def _assert_contract(client: LLMClient):
    assert isinstance(client, LLMClient)
    try:
        r = client.complete_json("sys", "user", {}, 5)
    except LLMError:
        return
    assert isinstance(r, LLMResponse)
    assert isinstance(r.text, str) and r.text


@pytest.mark.parametrize(
    "client",
    [
        FakeLLMClient(['{"a": 1}']),
        FakeLLMClient([LLMTimeoutError("t")]),
        FakeAdversarialClient(),
        RateLimitedClient(FakeLLMClient(["{}"]), max_rpm=5),
    ],
    ids=["fake-ok", "fake-error", "adversarial", "rate-limited"],
)
def test_fake_clients_follow_contract(client):
    _assert_contract(client)


def test_fake_client_records_calls_and_repeats_last_item():
    c = FakeLLMClient([LLMTimeoutError("x"), {"ok": True}])
    with pytest.raises(LLMTimeoutError):
        c.complete_json("s", "u1", {}, 1)
    assert c.complete_json("s", "u2", {}, 1).text == '{"ok": true}'
    assert c.complete_json("s", "u3", {}, 1).text == '{"ok": true}'
    assert [u for _, u in c.calls] == ["u1", "u2", "u3"]


def test_rate_limiter_blocks_over_limit_then_recovers():
    t = [0.0]
    c = RateLimitedClient(FakeLLMClient(["{}"]), max_rpm=2, clock=lambda: t[0])
    c.complete_json("s", "u", {}, 1)
    c.complete_json("s", "u", {}, 1)
    with pytest.raises(LLMRateLimitError):
        c.complete_json("s", "u", {}, 1)
    t[0] = 61.0
    c.complete_json("s", "u", {}, 1)


# --------------------------------------------------------------------------- chain


def test_build_chain_without_keys_is_template_mode():
    s = Settings(_env_file=None, llm_provider="gemini", llm_model_id="m", gemini_api_key=None)
    chain = build_chain(s)
    assert chain == []
    assert llm_mode(chain) == "template"


def test_build_chain_adversarial_and_dedup():
    s = Settings(
        _env_file=None, llm_provider="fake_adversarial", llm_fallback_provider="fake_adversarial"
    )
    chain = build_chain(s)
    assert [c.provider for c in chain] == ["fake_adversarial"]


def test_build_chain_with_keys_orders_primary_then_fallback():
    s = Settings(
        _env_file=None,
        llm_provider="gemini",
        llm_fallback_provider="anthropic",
        llm_model_id="some-model",
        gemini_api_key="k1",
        anthropic_api_key="k2",
    )
    assert [c.provider for c in build_chain(s)] == ["gemini", "anthropic"]


# --------------------------------------------------------------------------- HTTP mapping


class _Resp:
    def __init__(self, status: int, payload=None, headers=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _patch_post(monkeypatch, outcome):
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(http_providers.httpx, "post", fake_post)
    return seen


GEMINI_OK = {
    "candidates": [{"content": {"parts": [{"text": '{"subject": "x"}'}]}, "finishReason": "STOP"}],
    "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 7},
}
ANTHROPIC_OK = {
    "content": [{"type": "text", "text": '{"subject": "x"}'}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 11, "output_tokens": 7},
}


@pytest.mark.parametrize(
    "client_cls,ok_payload",
    [(GeminiClient, GEMINI_OK), (AnthropicClient, ANTHROPIC_OK)],
    ids=["gemini", "anthropic"],
)
class TestHttpProviders:
    def test_success_parses_text_and_usage_and_keeps_key_out_of_url(
        self, monkeypatch, client_cls, ok_payload
    ):
        seen = _patch_post(monkeypatch, _Resp(200, ok_payload))
        r = client_cls("SECRET-KEY", "model-x").complete_json("s", "u", {}, 3)
        assert r.text == '{"subject": "x"}'
        assert (r.prompt_tokens, r.completion_tokens) == (11, 7)
        assert "SECRET-KEY" not in seen["url"]
        assert "SECRET-KEY" in seen["headers"].values()

    @pytest.mark.parametrize(
        "outcome,error",
        [
            (httpx.ReadTimeout("slow"), LLMTimeoutError),
            (httpx.ConnectError("down"), LLMUnavailableError),
            (_Resp(500, {}), LLMUnavailableError),
            (_Resp(400, {}), LLMUnavailableError),
            (_Resp(200, None), LLMInvalidOutputError),
        ],
        ids=["timeout", "network", "5xx", "4xx", "non-json"],
    )
    def test_failures_map_to_typed_errors(
        self, monkeypatch, client_cls, ok_payload, outcome, error
    ):
        _patch_post(monkeypatch, outcome)
        with pytest.raises(error):
            client_cls("k", "m").complete_json("s", "u", {}, 3)

    def test_429_carries_retry_after(self, monkeypatch, client_cls, ok_payload):
        _patch_post(monkeypatch, _Resp(429, {}, {"retry-after": "3"}))
        with pytest.raises(LLMRateLimitError) as exc:
            client_cls("k", "m").complete_json("s", "u", {}, 3)
        assert exc.value.retry_after_s == 3.0

    def test_missing_key_is_unavailable(self, monkeypatch, client_cls, ok_payload):
        with pytest.raises(LLMUnavailableError):
            client_cls("", "m")


def test_gemini_safety_and_empty(monkeypatch):
    _patch_post(monkeypatch, _Resp(200, {"candidates": [{"finishReason": "SAFETY"}]}))
    with pytest.raises(LLMRefusalError):
        GeminiClient("k", "m").complete_json("s", "u", {}, 3)
    _patch_post(monkeypatch, _Resp(200, {"candidates": []}))
    with pytest.raises(LLMInvalidOutputError):
        GeminiClient("k", "m").complete_json("s", "u", {}, 3)


def test_anthropic_refusal(monkeypatch):
    _patch_post(monkeypatch, _Resp(200, {"content": [], "stop_reason": "refusal"}))
    with pytest.raises(LLMRefusalError):
        AnthropicClient("k", "m").complete_json("s", "u", {}, 3)


@pytest.mark.live
def test_live_primary_provider_returns_json():
    s = Settings()
    chain = build_chain(s)
    if not chain or os.environ.get("CI"):
        pytest.skip("no live LLM provider configured")
    r = chain[0].complete_json("Reply with JSON only.", 'Return {"ok": true}', {}, s.llm_timeout_s)
    assert "ok" in r.text
