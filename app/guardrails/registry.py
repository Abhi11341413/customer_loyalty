"""Default check list. Adding a check = new file in checks/ + one line here (§3.2).

Owner: M3.

Not implemented (cut list / OPEN-6): TONE_SEMANTIC and UNSUPPORTED_CLAIM_SEMANTIC
(LLM-as-judge, WARN-only). SENSITIVE_INPUT is enforced by re-running PII_LEAKAGE and
BLOCKED_LANGUAGE on every reviewer edit.
"""

from __future__ import annotations

from app.generation.content import TemplateStore
from app.guardrails.base import GuardrailCheck, GuardrailResources
from app.guardrails.checks.context import (
    ConsentStillValidCheck,
    DuplicateOutreachCheck,
    LowConfidenceSegmentCheck,
)
from app.guardrails.checks.grounding import (
    AmountGroundedCheck,
    DateGroundedCheck,
    NumberGroundedCheck,
)
from app.guardrails.checks.language import (
    BlockedLanguageCheck,
    FactContradictionCheck,
    ToneKeywordsCheck,
)
from app.guardrails.checks.length import LengthLimitsCheck
from app.guardrails.checks.offers import OfferIdValidCheck
from app.guardrails.checks.pii import PiiLeakageCheck
from app.guardrails.checks.required_text import DisclaimerPresentCheck, SupportPathPresentCheck
from app.guardrails.checks.schema import SchemaValidCheck
from app.guardrails.checks.slots import UnknownSlotCheck


def default_checks(res: GuardrailResources, templates: TemplateStore) -> list[GuardrailCheck]:
    cfg = res.config
    return [
        # mandatory (BLOCK)
        SchemaValidCheck(),
        UnknownSlotCheck(),
        AmountGroundedCheck(),
        DateGroundedCheck(),
        NumberGroundedCheck(),
        OfferIdValidCheck(cfg),
        BlockedLanguageCheck(cfg),
        PiiLeakageCheck(cfg),
        DisclaimerPresentCheck(set(res.disclaimers.texts)),
        SupportPathPresentCheck(),
        ConsentStillValidCheck(),
        DuplicateOutreachCheck(),
        FactContradictionCheck(cfg),
        # advisory (WARN)
        ToneKeywordsCheck(cfg),
        LengthLimitsCheck(templates),
        LowConfidenceSegmentCheck(),
    ]
