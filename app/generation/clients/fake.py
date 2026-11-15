"""FakeLLMClient (scripted, for tests) and FakeAdversarialClient (demo C0008).

Owner: M3.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable

from app.generation.clients.base import LLMError, LLMResponse

Script = str | dict | LLMError | Callable[[str, str], str | dict]


class FakeLLMClient:
    """Returns scripted outputs in order; an ``LLMError`` item is raised instead.

    A dict is serialised to JSON; a callable receives (system, user). When the script
    is exhausted the last item repeats. ``calls`` records every (system, user) seen.
    """

    def __init__(
        self, script: Iterable[Script], provider: str = "fake", model_id: str = "fake-llm"
    ):
        self.script = list(script)
        if not self.script:
            raise ValueError("FakeLLMClient needs at least one scripted output")
        self.provider = provider
        self.model_id = model_id
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str, schema: dict, timeout_s: float) -> LLMResponse:
        idx = min(len(self.calls), len(self.script) - 1)
        self.calls.append((system, user))
        item = self.script[idx]
        if callable(item) and not isinstance(item, LLMError):
            item = item(system, user)
        if isinstance(item, LLMError):
            raise item
        text = json.dumps(item) if isinstance(item, dict) else item
        return LLMResponse(text=text, provider=self.provider, model_id=self.model_id, latency_ms=1)


def _adversarial_output(system: str, user: str) -> dict:
    """Echo the objective from the prompt but invent a discount, deadline and threat."""
    objective = "REENGAGEMENT"
    marker = '"objective": "'
    if marker in user:
        objective = user.split(marker, 1)[1].split('"', 1)[0]
    return {
        "subject": "Special 20% off just for you, {{first_name}}",
        "body": (
            "Hi {{first_name}},\n\nWe noticed you have not been using your plan much. "
            "Get 20% off your next bill and a free upgrade! Offer code OFF-SECRET-20. "
            "Please pay within 24 hours or face legal action.\n\n{{cta}}\n\n"
            "Customer Care Team"
        ),
        "customer_segment": "DECLINING_ACTIVITY",
        "communication_objective": objective,
        "facts_used": ["first_name", "cta"],
        "offer_id": "OFF-SECRET-20",
        "disclaimer_keys": [],
    }


class FakeAdversarialClient(FakeLLMClient):
    """Demo toggle LLM_PROVIDER=fake_adversarial (§16 C0008): always unsafe output."""

    def __init__(self) -> None:
        super().__init__([_adversarial_output], provider="fake_adversarial", model_id="adversarial")
