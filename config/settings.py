"""pydantic-settings: env vars, paths, LLM provider, as_of default.

Owner: ALL (shared). Any member may add a key; it must also be added to .env.example
with a comment. Secrets use SecretStr so they are masked in repr/logs.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Typed application settings. Secrets are SecretStr so they never appear in repr/logs."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data' / 'app.db').as_posix()}"
CONFIG_DIR = PROJECT_ROOT / "config"
POLICIES_DIR = CONFIG_DIR / "policies"
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    database_url: str = f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"
    as_of_date: date = date(2026, 11, 15)

    llm_provider: str = "template"
    llm_model_id: str = ""
    llm_fallback_provider: str = "template"
    llm_timeout_s: float = 20.0
    llm_timeout_s: float = 20
    llm_max_rpm: int = 10
    llm_debug_log: bool = False
    gemini_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"

    backend_url: str = "http://localhost:8000"
    outbox_dir: Path = PROJECT_ROOT / "outbox"
    config_dir: Path = PROJECT_ROOT / "config"

    # Temporary (M4): wire scripted placeholder components for the parts owned by M1/M2/M3
    # that are not implemented yet, so the API/UI/review/delivery flow can be exercised.
    # Remove once CP1/CP2 land. Review, approval and the delivery gate are never stubbed.
    pipeline_stubs: bool = False
    outbox_dir: str = "outbox"


@lru_cache
def get_settings() -> Settings:
    """Return the cached process-wide settings."""
    return Settings()
