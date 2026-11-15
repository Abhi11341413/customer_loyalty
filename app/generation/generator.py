"""MessageGenerator: prompt -> JSON -> RawDraft, retries, fallback (FR-04, §8.2).

Owner: M3.

The generator receives only ``LLMInput`` + ``StrategyDecision`` (no DB, no repositories,
§3.4). It never raises for provider problems: the worst case is a TemplateOnly draft,
with every failed attempt recorded in ``RawDraft.fallback_events`` (audited by M4 as
LLM_FALLBACK). It does NOT judge content — wrong facts in a schema-valid reply are left
for the guardrails to BLOCK, so they are visible to the reviewer and in evaluation.

Failure handling per provider (§8.2):
- timeout / 5xx / network: retry once after a short backoff, then next provider
- 429: honour Retry-After up to ``max_retry_after_s`` once, else next provider
- invalid JSON / schema mismatch / wrong objective echo: one repair retry with the
  error appended, then next provider
- provider safety refusal: next provider
- INSUFFICIENT_INPUT sentinel: straight to TemplateOnly
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

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
from app.generation.clients.template_only import TemplateOnlyGenerator
from app.generation.content import TemplateStore
from app.generation.prompts.registry import PromptRegistry, RenderedPrompt
from app.schemas.enums import NON_DRAFT_OBJECTIVES
from app.schemas.generation import (
    INSUFFICIENT_INPUT_SENTINEL,
    FallbackEvent,
    LLMDraftOutput,
    LLMInput,
    RawDraft,
)
from app.schemas.policy import StrategyDecision

log = logging.getLogger(__name__)

OUTPUT_SCHEMA: dict = LLMDraftOutput.model_json_schema()
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class GenerationRequestError(ValueError):
    """Caller bug: asked to generate for a non-draft objective or mismatched inputs."""


class _InsufficientInput(Exception):
    pass


def parse_llm_json(text: str, llm_input: LLMInput) -> LLMDraftOutput:
    """Parse and validate a model reply. Raises LLMInvalidOutputError / _InsufficientInput."""
    cleaned = _FENCE_RE.sub("", text.strip()).strip()
    if not cleaned.startswith("{"):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMInvalidOutputError("reply is not a JSON object")
        cleaned = cleaned[start : end + 1]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMInvalidOutputError(f"invalid JSON: {exc.msg} at char {exc.pos}") from exc
    if not isinstance(data, dict):
        raise LLMInvalidOutputError("reply JSON is not an object")
    if str(data.get("subject", "")).strip() == INSUFFICIENT_INPUT_SENTINEL:
        raise _InsufficientInput()
    try:
        out = LLMDraftOutput.model_validate(data)
    except ValidationError as exc:
        errs = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise LLMInvalidOutputError(f"schema mismatch: {errs}") from exc
    if out.communication_objective != str(llm_input.objective):
        raise LLMInvalidOutputError(
            f"communication_objective must be {llm_input.objective!s}, "
            f"got {out.communication_objective!r}"
        )
    return out


class MessageGenerator:
    def __init__(
        self,
        clients: list[LLMClient],
        templates: TemplateStore,
        prompts: PromptRegistry,
        timeout_s: float = 20.0,
        max_retry_after_s: float = 10.0,
        backoff_s: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        debug_dir: Path | None = None,
    ) -> None:
        self._clients = list(clients)
        self._templates = templates
        self._prompts = prompts
        self._template_only = TemplateOnlyGenerator(templates)
        self._timeout_s = timeout_s
        self._max_retry_after_s = max_retry_after_s
        self._backoff_s = backoff_s
        self._sleep = sleep
        self._debug_dir = debug_dir

    @property
    def mode(self) -> str:
        return self._clients[0].provider if self._clients else "template"

    def generate(
        self,
        llm_input: LLMInput,
        strategy: StrategyDecision,
        feedback: list[str] | None = None,
        force_template: bool = False,
    ) -> RawDraft:
        """Produce a RawDraft. ``feedback`` = guardrail messages for a regeneration."""
        if strategy.objective in NON_DRAFT_OBJECTIVES or strategy.template_id is None:
            raise GenerationRequestError(f"objective {strategy.objective} does not produce drafts")
        if strategy.objective != llm_input.objective:
            raise GenerationRequestError("StrategyDecision and LLMInput objectives differ")
        template = self._templates.get(strategy.template_id)
        if template.objective != strategy.objective:
            raise GenerationRequestError(
                f"template {template.template_id} is for {template.objective}"
            )

        events: list[FallbackEvent] = []
        attempts = 0
        if not force_template:
            prompt = self._prompts.render(llm_input, feedback=feedback)
            for client in self._clients:
                result, n = self._try_client(client, prompt, llm_input, feedback, events)
                attempts += n
                if result is _INSUFFICIENT:
                    break
                if result is not None:
                    output, response = result
                    return self._to_raw(output, response, llm_input, template, events, attempts)

        if events:
            log.warning(
                "LLM fallback to template",
                extra={"events": [e.error_type for e in events], "template": template.ref},
            )
        return self._template_only.generate(llm_input, template, events, attempts)

    # ------------------------------------------------------------------ internals

    def _try_client(
        self,
        client: LLMClient,
        prompt: RenderedPrompt,
        llm_input: LLMInput,
        feedback: list[str] | None,
        events: list[FallbackEvent],
    ):
        """Return ((output, response) | None | _INSUFFICIENT, attempts_made)."""
        attempts = 0
        transient_retry_used = False
        repair_used = False
        current = prompt
        while True:
            attempts += 1
            try:
                response = client.complete_json(
                    current.system, current.user, OUTPUT_SCHEMA, self._timeout_s
                )
                self._debug_log(client, current, response.text)
                return (parse_llm_json(response.text, llm_input), response), attempts
            except _InsufficientInput:
                events.append(self._event(client, "INSUFFICIENT_INPUT", ""))
                return _INSUFFICIENT, attempts
            except LLMInvalidOutputError as exc:
                events.append(self._event(client, exc))
                if repair_used:
                    return None, attempts
                repair_used = True
                current = self._prompts.render(llm_input, feedback=feedback, repair_error=str(exc))
            except LLMRateLimitError as exc:
                events.append(self._event(client, exc))
                wait = exc.retry_after_s
                if transient_retry_used or wait is None or wait > self._max_retry_after_s:
                    return None, attempts
                transient_retry_used = True
                self._sleep(wait)
            except (LLMTimeoutError, LLMUnavailableError) as exc:
                events.append(self._event(client, exc))
                if transient_retry_used:
                    return None, attempts
                transient_retry_used = True
                self._sleep(self._backoff_s)
            except LLMRefusalError as exc:
                events.append(self._event(client, exc))
                return None, attempts
            except LLMError as exc:  # any other typed error: move on
                events.append(self._event(client, exc))
                return None, attempts
            except Exception as exc:  # LSP violation by a client: never crash the request
                log.exception("LLM client %s raised an untyped exception", client.provider)
                events.append(self._event(client, "UNEXPECTED_ERROR", type(exc).__name__))
                return None, attempts

    @staticmethod
    def _event(client: LLMClient, err: Exception | str, detail: str | None = None) -> FallbackEvent:
        if isinstance(err, Exception):
            return FallbackEvent(
                provider=client.provider,
                model_id=client.model_id,
                error_type=type(err).__name__,
                detail=(str(err) if detail is None else detail)[:200],
            )
        return FallbackEvent(
            provider=client.provider, model_id=client.model_id, error_type=err, detail=detail or ""
        )

    def _to_raw(
        self,
        out: LLMDraftOutput,
        response: LLMResponse,
        llm_input: LLMInput,
        template,
        events: list[FallbackEvent],
        attempts: int,
    ) -> RawDraft:
        return RawDraft(
            subject=out.subject.strip(),
            body=out.body.strip(),
            objective=llm_input.objective,
            offer_id=out.offer_id,
            facts_used=out.facts_used,
            disclaimer_keys=out.disclaimer_keys,
            communication_objective=out.communication_objective,
            template_id=template.template_id,
            template_version=template.version,
            prompt_version=self._prompts.version,
            model_provider=response.provider,
            model_id=response.model_id,
            fallback_events=list(events),
            llm_attempts=attempts,
            llm_latency_ms=response.latency_ms,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
        )

    def _debug_log(self, client: LLMClient, prompt: RenderedPrompt, reply: str) -> None:
        """Full prompt/response only when LLM_DEBUG_LOG=true (dev; logs/ is git-ignored)."""
        if self._debug_dir is None:
            return
        try:
            self._debug_dir.mkdir(parents=True, exist_ok=True)
            name = f"{int(time.time() * 1000)}_{client.provider}.json"
            (self._debug_dir / name).write_text(
                json.dumps(
                    {"system": prompt.system, "user": prompt.user, "reply": reply},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            log.warning("could not write LLM debug log")


_INSUFFICIENT = object()
