"""GenAI layer: LLM clients + fallback chain, prompts, generator, slot renderer (M3).

Owner: M3. Public entry points: ``build_generator`` (wiring helper for M4's container),
``MessageGenerator``, ``SlotRenderer``, ``compute_content_hash``, ``cta_text``.
"""

from __future__ import annotations

from app.generation.clients.chain import build_chain
from app.generation.content import DisclaimerStore, TemplateStore, cta_text
from app.generation.generator import MessageGenerator
from app.generation.prompts.registry import PromptRegistry
from app.generation.renderer import SlotRenderer, apply_edit, compute_content_hash
from config.settings import PROJECT_ROOT, Settings

__all__ = [
    "MessageGenerator",
    "SlotRenderer",
    "apply_edit",
    "build_generator",
    "build_renderer",
    "compute_content_hash",
    "cta_text",
]


def build_generator(settings: Settings) -> MessageGenerator:
    """Production wiring from settings (call once, from app/core/container.py)."""
    debug_dir = PROJECT_ROOT / "logs" / "llm_debug" if settings.llm_debug_log else None
    return MessageGenerator(
        clients=build_chain(settings),
        templates=TemplateStore(),
        prompts=PromptRegistry(),
        timeout_s=settings.llm_timeout_s,
        debug_dir=debug_dir,
    )


def build_renderer() -> SlotRenderer:
    return SlotRenderer(DisclaimerStore())
