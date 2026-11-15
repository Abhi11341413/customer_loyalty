"""Load and validate policy YAML into Pydantic config; compute version hash.

Owner: M4. Policy *content* is owned by M1/M2/M3 (one YAML per area); this module only loads
it and fingerprints it so every run can record which config produced it (FR-09).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class PolicyConfigError(Exception):
    """Raised when a policy file is missing or does not match its schema."""


def file_version(path: Path) -> str:
    """Short content hash, e.g. 'segments.yaml@3f9a1c2'. 'missing' if the file is absent."""
    if not path.exists():
        return f"{path.name}@missing"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:7]
    return f"{path.name}@{digest}"


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping; an empty/comment-only file yields {}."""
    if not path.exists():
        raise PolicyConfigError(f"Policy file not found: {path.name}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PolicyConfigError(f"Invalid YAML in {path.name}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise PolicyConfigError(f"{path.name} must contain a mapping at the top level")
    return data


def load_policy(path: Path, model: type[T]) -> T:
    """Load a YAML file and validate it into `model` (fails loudly at startup on typos)."""
    data = load_yaml(path)
    try:
        return model.model_validate(data)
    except Exception as exc:  # pydantic.ValidationError, re-raised with the file name
        raise PolicyConfigError(f"{path.name} does not match {model.__name__}: {exc}") from exc


def ruleset_version(config_dir: Path) -> str:
    """Combined fingerprint of every policy YAML, for /health and audit payloads."""
    policies = sorted((config_dir / "policies").glob("*.yaml"))
    digest = hashlib.sha256()
    for path in policies:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return f"policies@{digest.hexdigest()[:7]}"
