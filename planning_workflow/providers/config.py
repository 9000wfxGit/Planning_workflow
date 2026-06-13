"""Configuration loading for local backend runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    repo_root: Path = Field(default=Path("."))
    projects_dir_name: str = "projects"
    deepseek_api_key: str = Field(default="", validation_alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        validation_alias=AliasChoices("DEEPSEEK_BASE_URL", "DEEPSEEK_API_BASE_URL"),
    )
    deepseek_model: str = Field(default="deepseek-v4-pro", validation_alias="DEEPSEEK_MODEL")
    deepseek_thinking: str = Field(default="enabled", validation_alias="DEEPSEEK_THINKING")
    deepseek_reasoning_effort: str = Field(
        default="high", validation_alias="DEEPSEEK_REASONING_EFFORT"
    )
    deepseek_max_tokens: int = Field(default=20000, validation_alias="DEEPSEEK_MAX_TOKENS")
    deepseek_timeout_seconds: float = Field(
        default=60.0, validation_alias="DEEPSEEK_TIMEOUT_SECONDS"
    )
    search_provider_chain: str = Field(default="searxng,brave", validation_alias="SEARCH_PROVIDER_CHAIN")
    searxng_base_url: str = Field(default="http://localhost:8080", validation_alias="SEARXNG_BASE_URL")
    brave_search_api_key: str = Field(default="", validation_alias="BRAVE_SEARCH_API_KEY")
    run_live_deepseek_tests: bool = Field(default=False, validation_alias="RUN_LIVE_DEEPSEEK_TESTS")
    run_live_search_tests: bool = Field(default=False, validation_alias="RUN_LIVE_SEARCH_TESTS")

    @field_validator("deepseek_model")
    @classmethod
    def _reject_deprecated_model_names(cls, value: str) -> str:
        if value in {"deepseek-reasoner", "deepseek-chat"}:
            return "deepseek-v4-pro"
        return value

    @field_validator("deepseek_thinking")
    @classmethod
    def _normalize_thinking(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return "enabled"
        if normalized in {"0", "false", "no", "off"}:
            return "disabled"
        if normalized not in {"enabled", "disabled"}:
            return "enabled"
        return normalized

    @property
    def search_providers(self) -> list[str]:
        return [
            item.strip().lower()
            for item in self.search_provider_chain.split(",")
            if item.strip()
        ]


def load_settings(repo_root: str | Path = ".") -> Settings:
    root = Path(repo_root).resolve()
    values: dict[str, Any] = parse_env_file(root / ".env")
    return Settings(**values, repo_root=root)
