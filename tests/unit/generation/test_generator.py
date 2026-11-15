"""MessageGenerator: parsing, retries, repair and fallback (§8.2, §15.2 LLM cases)."""

import json

import pytest

from app.generation.clients.base import (
    LLMRateLimitError,
    LLMRefusalError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.generation.clients.fake import FakeLLMClient
from app.generation.generator import GenerationRequestError, MessageGenerator, parse_llm_json
from app.generation.prompts.registry import PromptRegistry
from app.schemas.enums import Objective
from tests.support import m3

OBJ = Objective.BILLING_REMINDER_COURTEOUS
GOOD = m3.good_llm_reply(OBJ)


def make_gen(*clients, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    return MessageGenerator(
        list(clients), m3.templates(), PromptRegistry(), sleep=sleeps.append, backoff_s=0.5
    )


def gen(objective=OBJ, *clients, **kw):
    return make_gen(*clients, **kw).generate(m3.llm_input(objective), m3.strategy(objective))


def test_valid_reply_is_parsed_into_raw_draft():
    client = FakeLLMClient([GOOD], provider="gemini", model_id="m-1")
    raw = gen(OBJ, client)
    assert raw.model_provider == "gemini" and raw.model_id == "m-1"
    assert raw.body == GOOD["body"]
    assert raw.prompt_version and raw.prompt_version.startswith("v1+")
    assert raw.template_id == "billing_reminder_stage1"
    assert raw.fallback_events == [] and raw.llm_attempts == 1


def test_code_fenced_json_is_accepted():
    raw = gen(OBJ, FakeLLMClient(["```json\n" + json.dumps(GOOD) + "\n```"]))
    assert raw.model_provider == "fake"


def test_no_clients_means_template_only():
    raw = gen(OBJ)
    assert raw.is_template_only and raw.model_id == "template-only"
    assert raw.prompt_version is None and raw.fallback_events == []


def test_empty_reply_repairs_then_falls_back_to_template():
    client = FakeLLMClient(["", ""])
    raw = gen(OBJ, client)
    assert raw.is_template_only
    assert len(client.calls) == 2  # original + one repair
    assert "previous reply was not valid" in client.calls[1][1]
    assert [e.error_type for e in raw.fallback_events] == ["LLMInvalidOutputError"] * 2


def test_invalid_json_then_repaired_reply_succeeds():
    client = FakeLLMClient(["not json at all", GOOD])
    raw = gen(OBJ, client)
    assert not raw.is_template_only and raw.llm_attempts == 2
    assert len(raw.fallback_events) == 1


def test_schema_mismatch_short_body_triggers_repair():
    bad = {**GOOD, "body": "too short"}
    client = FakeLLMClient([bad, bad])
    assert gen(OBJ, client).is_template_only
    assert "schema mismatch" in client.calls[1][1]


def test_wrong_objective_echo_is_invalid_output():
    bad = {**GOOD, "communication_objective": "APPRECIATION"}
    raw = gen(OBJ, FakeLLMClient([bad, bad]))
    assert raw.is_template_only


def test_timeout_retries_once_with_backoff_then_falls_back():
    sleeps: list[float] = []
    client = FakeLLMClient([LLMTimeoutError("slow")])
    raw = gen(OBJ, client, sleeps=sleeps)
    assert raw.is_template_only
    assert len(client.calls) == 2 and sleeps == [0.5]
    assert {e.error_type for e in raw.fallback_events} == {"LLMTimeoutError"}


def test_unavailable_then_success_on_retry():
    raw = gen(OBJ, FakeLLMClient([LLMUnavailableError("503"), GOOD]))
    assert not raw.is_template_only


def test_429_with_short_retry_after_waits_and_retries():
    sleeps: list[float] = []
    raw = gen(OBJ, FakeLLMClient([LLMRateLimitError(retry_after_s=2), GOOD]), sleeps=sleeps)
    assert not raw.is_template_only and sleeps == [2]


def test_429_with_long_or_missing_retry_after_falls_back_immediately():
    for err in (LLMRateLimitError(retry_after_s=60), LLMRateLimitError()):
        client = FakeLLMClient([err])
        sleeps: list[float] = []
        assert gen(OBJ, client, sleeps=sleeps).is_template_only
        assert len(client.calls) == 1 and sleeps == []


def test_refusal_moves_to_next_provider():
    first = FakeLLMClient([LLMRefusalError("no")], provider="p1")
    second = FakeLLMClient([GOOD], provider="p2")
    raw = gen(OBJ, first, second)
    assert raw.model_provider == "p2"
    assert raw.fallback_events[0].provider == "p1"


def test_insufficient_input_sentinel_goes_straight_to_template():
    first = FakeLLMClient([{"subject": "INSUFFICIENT_INPUT", "body": ""}], provider="p1")
    second = FakeLLMClient([GOOD], provider="p2")
    raw = gen(OBJ, first, second)
    assert raw.is_template_only and second.calls == []
    assert raw.fallback_events[-1].error_type == "INSUFFICIENT_INPUT"


def test_untyped_client_exception_never_crashes():
    def boom(system, user):
        raise RuntimeError("vendor bug")

    raw = gen(OBJ, FakeLLMClient([boom]))
    assert raw.is_template_only
    assert raw.fallback_events[0].error_type == "UNEXPECTED_ERROR"


def test_invented_offer_is_not_judged_by_generator():
    """Content problems are left for guardrails (visible to the reviewer)."""
    bad = {**GOOD, "offer_id": "OFF-FAKE-1"}
    raw = gen(OBJ, FakeLLMClient([bad]))
    assert raw.offer_id == "OFF-FAKE-1" and not raw.is_template_only


def test_force_template_skips_llm():
    client = FakeLLMClient([GOOD])
    raw = make_gen(client).generate(m3.llm_input(OBJ), m3.strategy(OBJ), force_template=True)
    assert raw.is_template_only and client.calls == []


def test_feedback_is_included_in_prompt_for_regeneration():
    client = FakeLLMClient([GOOD])
    make_gen(client).generate(m3.llm_input(OBJ), m3.strategy(OBJ), feedback=["Remove '20% off'"])
    assert "Remove '20% off'" in client.calls[0][1]


def test_prompt_contains_only_llm_input_data():
    client = FakeLLMClient([GOOD])
    li = m3.llm_input(OBJ)
    make_gen(client).generate(li, m3.strategy(OBJ))
    system, user = client.calls[0]
    assert "Ravi" in user and "{{amount_due}}" in user
    assert "@" not in user and "C0005" not in user


@pytest.mark.parametrize(
    "objective", [Objective.NO_CONTACT, Objective.ESCALATE, Objective.NO_CONTACT_BY_POLICY]
)
def test_non_draft_objectives_are_rejected(objective):
    li = m3.llm_input(OBJ).model_copy(update={"objective": objective})
    st = m3.strategy(OBJ).model_copy(update={"objective": objective, "template_id": None})
    with pytest.raises(GenerationRequestError):
        make_gen().generate(li, st)


def test_strategy_and_input_objective_mismatch_rejected():
    with pytest.raises(GenerationRequestError):
        make_gen().generate(m3.llm_input(OBJ), m3.strategy(Objective.BILLING_REMINDER_FIRM))


@pytest.mark.parametrize("objective", m3.DRAFT_OBJECTIVES)
def test_template_fallback_works_for_every_objective(objective):
    raw = gen(objective)
    assert raw.objective == objective and raw.is_template_only


def test_parse_llm_json_extracts_object_from_chatter():
    text = "Sure! Here it is: " + json.dumps(GOOD) + " Hope that helps."
    assert parse_llm_json(text, m3.llm_input(OBJ)).subject == GOOD["subject"]
