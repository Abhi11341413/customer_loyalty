# M3 integration notes (generation + guardrails)

How M2 and M4 plug into the M3 layer. Contracts live in `app/schemas/generation.py` and
`app/schemas/validation.py`.

## For M2 — building `LLMInput` (`app/policy/llm_input.py`)

Examples of the exact shape for every objective: `tests/fixtures/contracts/llm_input_*.json`
(the integration test fails if they stop validating).

`allowed_slots` vocabulary (templates and prompts use only these):

| Slot | Value (display string) | Needed for |
|---|---|---|
| `first_name` | "Ravi" | all |
| `cta` | `app.generation.cta_text(strategy.cta_key)` | all |
| `plan_name` | "Postpaid 499" | optional (appreciation / re-engagement use it when present) |
| `amount_due` | "₹599.00" | billing |
| `due_date` | "10 Nov 2026" | billing |
| `bill_period` | "October 2026" | billing |
| `days_overdue` | bare integer, "26" | stage 3 |
| `support_path` | sentence ending with ".", e.g. "reply to this email or visit the Help section of your account." | billing (FR-06) — required |

Offer slots (`offer_title`, `offer_value`, `offer_valid_to`, `offer_terms`) are derived by
M3 from `LLMInput.offer` (`VerifiedOffer`); you do not need to add them.

`tone` = `ToneSpec(name=strategy.tone, rules=ToneStore().rules_for(strategy.tone))`
(`app/generation/content.py`, rules in `config/policies/tone.yaml`).
`required_disclaimers` = `strategy.required_disclaimer_keys` (keys in `disclaimers.yaml`:
`already_paid`, `support_dispute_path`, `need_help`, `offer_terms`, `unsubscribe`).
CTA keys in `config/templates/_ctas.yaml`: `explore_account`, `view_reward`, `view_plan`,
`reactivate`, `pay_bill`, `pay_or_contact`. Template ids = file names in `config/templates/`.

## For M4 — orchestrator / review / delivery

```python
from app.generation import build_generator, build_renderer, apply_edit, compute_content_hash
from app.guardrails.runner import GuardrailRunner
from app.schemas.validation import ValidationContext

generator = build_generator(settings)        # once, in app/core/container.py
renderer = build_renderer()
guardrails = GuardrailRunner.default()

raw = generator.generate(llm_input, strategy)                 # never raises for LLM failures
draft = renderer.render(raw, llm_input)                       # RenderedDraft
report = guardrails.validate(draft, ValidationContext(
    llm_input=llm_input,
    contact_allowed=contact.allowed, contact_reasons=contact.reasons,
    duplicate_outreach=<pending/delivered draft for same customer+objective?>,
    confidence_band=classification.confidence_band,
    shadow_agrees=classification.shadow.agrees if classification.shadow else None,
))
```

- Draft state: `report.overall` PASS/WARN → `PENDING_REVIEW`, BLOCK → `BLOCKED`,
  ESCALATE → `ESCALATED`. `report.approvable` is the approve-button condition.
- Audit (FR-09): `raw.template_id/template_version/prompt_version/model_provider/model_id`,
  `raw.llm_latency_ms/prompt_tokens/completion_tokens`, `draft.facts_used` **keys**,
  `report.guardrail_version`. Log one `LLM_FALLBACK` event per `raw.fallback_events` item.
- Edit (PATCH): `edited = apply_edit(draft, subject, body)` then validate again; approval
  binds to `edited.content_hash`. Always hash with `compute_content_hash`.
- Regenerate after BLOCK: `generator.generate(llm_input, strategy, feedback=[f.message for f in report.failures])`;
  after 2 failed regenerations offer `force_template=True` (§9.5).
- Health/UI banner: `generator.mode` → provider name or `"template"`.
- Demo C0008: `LLM_PROVIDER=fake_adversarial`.
- `ValidationContext` fields left `None` are reported in `report.checks_skipped`, never passed silently.
