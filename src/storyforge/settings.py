"""Validated process configuration for API, CLI, and application factories."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from storyforge.exceptions import ConfigurationError


def _boolean(value: str, *, name: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean value")


class Settings(BaseModel):
    """One immutable, explicit configuration snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./storyforge.db"
    llm_provider: Literal["mock", "openai-compatible"] = "mock"
    llm_model: str = "mock-storyforge-v1"
    llm_api_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr | None = None
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    llm_max_retries: int = Field(default=2, ge=0, le=10)
    llm_repair_retries: int = Field(default=1, ge=0, le=5)
    llm_retry_base_delay_seconds: float = Field(default=0.5, ge=0, le=30)
    mock_workflow_scenario: Literal["pass", "improve", "stagnate"] = "improve"
    mock_critic_scenario: Literal["normal", "death", "outline", "poor", "conflict"] = "normal"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_prefix: str = "/api/v1"
    default_page_size: int = Field(default=20, ge=1, le=100)
    maximum_page_size: int = Field(default=100, ge=1, le=500)
    max_revision_attempts: int = Field(default=3, ge=0, le=10)
    allow_debug_pause_nodes: bool = False
    include_error_detail_in_logs: bool = False
    max_request_body_bytes: int = Field(default=1_048_576, ge=1_024, le=10_485_760)
    max_chapter_content_chars: int = Field(default=500_000, ge=1_000, le=2_000_000)
    max_diff_chars: int = Field(default=50_000, ge=1_000, le=500_000)
    checkpoint_path: Path | None = None
    enable_http_logging: bool = True

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        """Reject unsafe production fallback and internally inconsistent limits."""
        if not self.database_url.strip():
            raise ConfigurationError("STORYFORGE_DATABASE_URL must not be empty")
        if not self.api_prefix.startswith("/") or self.api_prefix.endswith("/"):
            raise ConfigurationError(
                "STORYFORGE_API_PREFIX must start with '/' and not end with '/'"
            )
        if self.default_page_size > self.maximum_page_size:
            raise ConfigurationError("Default page size cannot exceed maximum page size")
        if self.environment == "production" and self.llm_provider == "mock":
            raise ConfigurationError("Production must explicitly configure a non-mock provider")
        if self.llm_provider == "openai-compatible":
            key = self.llm_api_key.get_secret_value() if self.llm_api_key is not None else ""
            if not key:
                raise ConfigurationError("OpenAI-compatible provider requires an API key")
            if not self.llm_model or self.llm_model.startswith("replace-with"):
                raise ConfigurationError("OpenAI-compatible provider requires a real model name")
        return self

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Read one settings snapshot without loading a .env file implicitly."""
        values = os.environ if environ is None else environ

        def value(name: str, legacy: str | None, default: str) -> str:
            current = values.get(f"STORYFORGE_{name}")
            if current is None and legacy is not None:
                current = values.get(legacy)
            return default if current is None else current

        key_value = value("LLM_API_KEY", "OPENAI_API_KEY", "")
        checkpoint = value("CHECKPOINT_PATH", None, "")
        try:
            return cls(
                environment=cast(
                    Literal["development", "test", "production"],
                    value("ENVIRONMENT", None, "development"),
                ),
                database_url=value("DATABASE_URL", "DATABASE_URL", "sqlite:///./storyforge.db"),
                llm_provider=cast(
                    Literal["mock", "openai-compatible"],
                    value("LLM_PROVIDER", None, "mock"),
                ),
                llm_model=value("LLM_MODEL", "OPENAI_MODEL", "mock-storyforge-v1"),
                llm_api_base_url=value(
                    "LLM_API_BASE_URL", "OPENAI_BASE_URL", "https://api.openai.com/v1"
                ),
                llm_api_key=SecretStr(key_value) if key_value else None,
                llm_timeout_seconds=float(
                    value("LLM_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS", "30")
                ),
                llm_max_retries=int(value("LLM_MAX_RETRIES", "LLM_MAX_RETRIES", "2")),
                llm_repair_retries=int(value("LLM_REPAIR_RETRIES", "LLM_REPAIR_RETRIES", "1")),
                llm_retry_base_delay_seconds=float(
                    value(
                        "LLM_RETRY_BASE_DELAY_SECONDS",
                        "LLM_RETRY_BASE_DELAY_SECONDS",
                        "0.5",
                    )
                ),
                mock_workflow_scenario=cast(
                    Literal["pass", "improve", "stagnate"],
                    value("MOCK_WORKFLOW_SCENARIO", None, "improve"),
                ),
                mock_critic_scenario=cast(
                    Literal["normal", "death", "outline", "poor", "conflict"],
                    value("MOCK_CRITIC_SCENARIO", None, "normal"),
                ),
                log_level=cast(
                    Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                    value("LOG_LEVEL", None, "INFO").upper(),
                ),
                api_prefix=value("API_PREFIX", None, "/api/v1"),
                default_page_size=int(value("DEFAULT_PAGE_SIZE", None, "20")),
                maximum_page_size=int(value("MAXIMUM_PAGE_SIZE", None, "100")),
                max_revision_attempts=int(value("MAX_REVISION_ATTEMPTS", None, "3")),
                allow_debug_pause_nodes=_boolean(
                    value("ALLOW_DEBUG_PAUSE_NODES", None, "false"),
                    name="STORYFORGE_ALLOW_DEBUG_PAUSE_NODES",
                ),
                include_error_detail_in_logs=_boolean(
                    value("INCLUDE_ERROR_DETAIL_IN_LOGS", None, "false"),
                    name="STORYFORGE_INCLUDE_ERROR_DETAIL_IN_LOGS",
                ),
                max_request_body_bytes=int(value("MAX_REQUEST_BODY_BYTES", None, "1048576")),
                max_chapter_content_chars=int(value("MAX_CHAPTER_CONTENT_CHARS", None, "500000")),
                max_diff_chars=int(value("MAX_DIFF_CHARS", None, "50000")),
                checkpoint_path=Path(checkpoint) if checkpoint else None,
                enable_http_logging=_boolean(
                    value("ENABLE_HTTP_LOGGING", None, "true"),
                    name="STORYFORGE_ENABLE_HTTP_LOGGING",
                ),
            )
        except ValueError as exc:
            raise ConfigurationError("StoryForge numeric or enum settings are invalid") from exc
