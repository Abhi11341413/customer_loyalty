"""M3 integration boundary (§12): LLMInput -> Generator -> SlotRenderer -> Guardrails.

Uses the JSON contract fixtures (tests/fixtures/contracts/llm_input_*.json) that M2's
LLMInput builder must be able to produce, plus FakeLLM / adversarial / failing clients.
"""

import json
from pathlib import Path

import pytest

from app.generation.clients.base import LLMTimeoutError
from app.generation.clients.fake import FakeAdversarialClient, FakeLLMClient
from app.generation.generator import MessageGenerator
from app.generation.prompts.registry import PromptRegistry
from app.generation.renderer import apply_edit, split_disclaimers
from app.schemas.enums import Objective, Severity
from app.schemas.generation import LLMInput
from tests.support import m3

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"


def load_fixture(objective: Objective) -> LLMInput:
    path = FIXTURES / f"llm_input_{objective.value.lower()}.json"
    return LLMInput.model_validate(json.loads(path.read_text(encoding="utf-8")))


def pipeline(objective: Objective, *clients, li: LLMInput | None = None, **ctx_kw):
    li = li or load_fixture(objective)
    gen = MessageGenerator(list(clients), m3.templates(), PromptRegistry(), sleep=lambda s: None)
    raw = gen.generate(li, m3.strategy(objective))
    draft = m3.renderer().render(raw, li)
    return raw, draft, m3.runner().validate(draft, m3.ctx(objective, li, **ctx_kw))


@pytest.mark.parametrize("objective", m3.DRAFT_OBJECTIVES)
def test_contract_fixture_matches_builder_and_has_no_pii(objective):
    li = load_fixture(objective)
    assert li == m3.llm_input(objective)
    dumped = li.model_dump_json()
    assert "@" not in dumped and "customer_id" not in dumped and "C0" not in dumped


@pytest.mark.parametrize("objective", m3.DRAFT_OBJECTIVES)
def test_llm_draft_passes_end_to_end(objective):
    client = FakeLLMClient([m3.good_llm_reply(objective)], provider="gemini")
    raw, draft, report = pipeline(objective, client)
    assert raw.model_provider == "gemini"
    assert report.overall is Severity.PASS, [f.message for f in report.failures]


@pytest.mark.parametrize("objective", m3.DRAFT_OBJECTIVES)
def test_llm_down_still_produces_a_passing_template_draft(objective):
    raw, draft, report = pipeline(objective, FakeLLMClient([LLMTimeoutError("down")]))
    assert raw.is_template_only and raw.fallback_events
    assert report.overall is Severity.PASS


def test_c0008_adversarial_output_is_blocked_with_expected_findings():
    raw, draft, report = pipeline(Objective.REENGAGEMENT, FakeAdversarialClient())
    assert report.overall is Severity.BLOCK and not report.approvable
    failed = {f.check_id for f in report.failures}
    assert {"OFFER_ID_VALID", "NUMBER_GROUNDED", "DATE_GROUNDED", "BLOCKED_LANGUAGE"} <= failed


def test_regeneration_with_feedback_then_clean():
    """BLOCK -> regenerate with findings fed back -> clean reply passes."""
    obj = Objective.REENGAGEMENT
    _, _, blocked = pipeline(obj, FakeAdversarialClient())
    feedback = [f.message for f in blocked.failures]
    client = FakeLLMClient([m3.good_llm_reply(obj)])
    li = load_fixture(obj)
    gen = MessageGenerator([client], m3.templates(), PromptRegistry())
    raw = gen.generate(li, m3.strategy(obj), feedback=feedback)
    assert "legal action" in client.calls[0][1]
    report = m3.runner().validate(m3.renderer().render(raw, li), m3.ctx(obj, li))
    assert report.overall is Severity.PASS


def test_reviewer_edit_is_revalidated():
    obj = Objective.BILLING_REMINDER_COURTEOUS
    _, draft, report = pipeline(obj)
    assert report.overall is Severity.PASS

    main, block = split_disclaimers(draft.body)
    polite = apply_edit(draft, draft.subject, draft.body.replace("quick reminder", "gentle note"))
    assert m3.runner().validate(polite, m3.ctx(obj)).overall is Severity.PASS
    assert polite.content_hash != draft.content_hash

    leaky = apply_edit(draft, draft.subject, draft.body + "\nCall 98765 43210.")
    assert m3.runner().validate(leaky, m3.ctx(obj)).overall is Severity.BLOCK

    stripped = apply_edit(draft, draft.subject, main)
    assert m3.runner().validate(stripped, m3.ctx(obj)).overall is Severity.BLOCK
