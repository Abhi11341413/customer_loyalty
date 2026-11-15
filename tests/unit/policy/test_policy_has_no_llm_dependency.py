"""app/policy/ must stay deterministic: no imports from the LLM layer (§6, rule 19)."""

import ast
from pathlib import Path

import pytest

POLICY_DIR = Path(__file__).resolve().parents[3] / "app" / "policy"
FORBIDDEN_PREFIXES = (
    "app.generation",
    "app.guardrails",
    "anthropic",
    "openai",
    "google.generativeai",
    "google.genai",
    "ollama",
    "mistralai",
    "httpx",
    "requests",
)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


@pytest.mark.parametrize("path", sorted(POLICY_DIR.glob("*.py")), ids=lambda p: p.name)
def test_no_llm_imports(path):
    bad = [n for n in _imports(path) if n.startswith(FORBIDDEN_PREFIXES)]
    assert not bad, f"{path.name} imports {bad}"
