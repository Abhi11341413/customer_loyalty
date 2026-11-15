"""Loaders for M3's policy-controlled content: templates, CTAs, disclaimers, tones.

Owner: M3.

All files are validated with Pydantic at load time (a YAML typo fails at startup, D7)
and versioned by a content hash. Hashes are computed on newline-normalised text so a
Windows checkout (core.autocrlf) yields the same version as Linux/macOS.
"""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.enums import Objective
from config.settings import CONFIG_DIR, POLICIES_DIR

TEMPLATES_DIR = CONFIG_DIR / "templates"

#: `{{ slot_name }}` — the only placeholder syntax the system understands.
SLOT_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class ContentConfigError(ValueError):
    """A content/config file is missing or invalid."""


def read_normalized(path: Path) -> str:
    """Read a text file with newlines normalised to "\\n"."""
    try:
        return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except FileNotFoundError as exc:
        raise ContentConfigError(f"Missing config file: {path}") from exc


def content_version(*texts: str) -> str:
    """Short, stable version id for one or more normalised texts."""
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:12]


def load_yaml(path: Path) -> tuple[dict, str]:
    """Return (parsed mapping, normalised text)."""
    text = read_normalized(path)
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ContentConfigError(f"{path.name}: top level must be a mapping")
    return data, text


def slots_in(text: str) -> set[str]:
    return set(SLOT_RE.findall(text))


# --------------------------------------------------------------------------- templates


class TemplateVariant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    when_offer: bool
    subject: str
    body: str

    @property
    def slots(self) -> set[str]:
        return slots_in(self.subject) | slots_in(self.body)


class MessageTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str
    version: str
    objective: Objective
    word_range: tuple[int, int]
    variants: list[TemplateVariant] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_range(self) -> MessageTemplate:
        lo, hi = self.word_range
        if not 0 < lo < hi:
            raise ValueError(f"{self.template_id}: invalid word_range {self.word_range}")
        return self

    @property
    def ref(self) -> str:
        return f"{self.template_id}@{self.version}"

    def select_variant(self, available_slots: set[str], has_offer: bool) -> TemplateVariant:
        """First variant matching the offer presence whose slots are all available."""
        for v in self.variants:
            if v.when_offer == has_offer and v.slots <= available_slots:
                return v
        missing = sorted(
            min(
                (v.slots - available_slots for v in self.variants if v.when_offer == has_offer),
                key=len,
                default={"<no variant for offer=" + str(has_offer) + ">"},
            )
        )
        raise ContentConfigError(
            f"Template {self.template_id}: no variant fits; missing slots {missing}"
        )


class TemplateStore:
    """All approved templates in config/templates/ (files starting with "_" excluded)."""

    def __init__(self, directory: Path = TEMPLATES_DIR) -> None:
        self._templates: dict[str, MessageTemplate] = {}
        for path in sorted(directory.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            data, _ = load_yaml(path)
            try:
                tpl = MessageTemplate.model_validate(data)
            except ValueError as exc:
                raise ContentConfigError(f"{path.name}: {exc}") from exc
            if tpl.template_id != path.stem:
                raise ContentConfigError(f"{path.name}: template_id must equal file name")
            self._templates[tpl.template_id] = tpl

    def get(self, template_id: str) -> MessageTemplate:
        try:
            return self._templates[template_id]
        except KeyError as exc:
            raise ContentConfigError(f"Unknown template_id: {template_id}") from exc

    def for_objective(self, objective: Objective) -> MessageTemplate:
        for tpl in self._templates.values():
            if tpl.objective == objective:
                return tpl
        raise ContentConfigError(f"No template for objective {objective}")

    def all(self) -> list[MessageTemplate]:
        return list(self._templates.values())


# --------------------------------------------------------------------------- CTAs


@lru_cache
def _ctas(path: Path = TEMPLATES_DIR / "_ctas.yaml") -> dict[str, str]:
    data, _ = load_yaml(path)
    ctas = data.get("ctas") or {}
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in ctas.items()):
        raise ContentConfigError("_ctas.yaml: ctas must map str -> str")
    return dict(ctas)


def cta_text(cta_key: str) -> str:
    """Approved CTA wording for a StrategyDecision.cta_key (for allowed_slots["cta"])."""
    try:
        return _ctas()[cta_key]
    except KeyError as exc:
        raise ContentConfigError(f"Unknown cta_key: {cta_key}") from exc


# --------------------------------------------------------------------------- disclaimers


class DisclaimerStore:
    def __init__(self, path: Path = POLICIES_DIR / "disclaimers.yaml") -> None:
        data, text = load_yaml(path)
        raw = data.get("disclaimers") or {}
        if not raw or not all(isinstance(v, str) and v.strip() for v in raw.values()):
            raise ContentConfigError("disclaimers.yaml: disclaimers must be non-empty strings")
        self.texts: dict[str, str] = {str(k): v.strip() for k, v in raw.items()}
        self.version = f"{data.get('version', '0')}+{content_version(text)}"

    def text(self, key: str) -> str:
        try:
            return self.texts[key]
        except KeyError as exc:
            raise ContentConfigError(f"Unknown disclaimer key: {key}") from exc


# --------------------------------------------------------------------------- tones


class ToneStore:
    def __init__(self, path: Path = POLICIES_DIR / "tone.yaml") -> None:
        data, text = load_yaml(path)
        tones = data.get("tones") or {}
        self.rules: dict[str, list[str]] = {
            str(name): [str(r) for r in (spec or {}).get("rules", [])]
            for name, spec in tones.items()
        }
        self.version = f"{data.get('version', '0')}+{content_version(text)}"

    def rules_for(self, tone: str) -> list[str]:
        try:
            return self.rules[tone]
        except KeyError as exc:
            raise ContentConfigError(f"Unknown tone: {tone}") from exc
