"""PromptRegistry: versioned system + user prompts (§8.6).

Owner: M3.

A prompt version is the triple (system_vN.txt, user_vN.j2, guidance_vN.yaml). The
recorded ``prompt_version`` is "vN+<hash>" so any edit to wording is visible in audit
(FR-09) even if someone forgets to bump N. Jinja2 uses StrictUndefined (fails loudly).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from app.generation.content import ContentConfigError, content_version, load_yaml, read_normalized
from app.schemas.generation import LLMInput

PROMPTS_DIR = Path(__file__).resolve().parent
DEFAULT_VERSION = "v1"


@dataclass(frozen=True)
class RenderedPrompt:
    system: str
    user: str
    version: str


class PromptRegistry:
    def __init__(self, version: str = DEFAULT_VERSION, directory: Path = PROMPTS_DIR) -> None:
        self._system = read_normalized(directory / f"system_{version}.txt").strip()
        user_src = read_normalized(directory / f"user_{version}.j2")
        guidance_data, guidance_text = load_yaml(directory / f"guidance_{version}.yaml")
        self._guidance: dict[str, str] = {
            str(k): " ".join(str(v).split())
            for k, v in (guidance_data.get("guidance") or {}).items()
        }
        env = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
        self._user = env.from_string(user_src)
        self.version = f"{version}+{content_version(self._system, user_src, guidance_text)}"

    def guidance_for(self, objective: str) -> str:
        try:
            return self._guidance[objective]
        except KeyError as exc:
            raise ContentConfigError(f"No prompt guidance for objective {objective}") from exc

    def render(
        self,
        llm_input: LLMInput,
        feedback: list[str] | None = None,
        repair_error: str | None = None,
    ) -> RenderedPrompt:
        """Build (system, user) for one LLM call. Only LLMInput content is included."""
        slot_names = sorted(llm_input.allowed_slots)
        if llm_input.offer is not None:
            slot_names = sorted(
                set(slot_names) | {"offer_title", "offer_value", "offer_valid_to", "offer_terms"}
            )
        user = self._user.render(
            input_json=json.dumps(llm_input.model_dump(mode="json"), ensure_ascii=False, indent=2),
            guidance=self.guidance_for(str(llm_input.objective)),
            skeleton=llm_input.template_skeleton,
            slot_list=", ".join("{{" + s + "}}" for s in slot_names),
            offer_id=llm_input.offer.offer_id if llm_input.offer else None,
            disclaimer_keys=", ".join(llm_input.required_disclaimers) or "(none)",
            forbidden=", ".join(llm_input.forbidden) or "(nothing extra)",
            objective=str(llm_input.objective),
            feedback=feedback or [],
            repair_error=repair_error,
        )
        return RenderedPrompt(system=self._system, user=user.strip() + "\n", version=self.version)
