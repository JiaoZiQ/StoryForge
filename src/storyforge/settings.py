"""Validated process configuration for API, CLI, and application factories."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from sqlalchemy import make_url

from storyforge.database import normalize_database_url
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
    database_url: str = Field(default="sqlite:///./storyforge.db", repr=False)
    llm_provider: Literal["mock", "openai-compatible"] = "mock"
    llm_model: str = "mock-storyforge-v1"
    llm_api_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr | None = None
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    llm_max_retries: int = Field(default=2, ge=0, le=10)
    llm_repair_retries: int = Field(default=1, ge=0, le=5)
    llm_retry_base_delay_seconds: float = Field(default=0.5, ge=0, le=30)
    embedding_provider: Literal["mock", "openai-compatible"] = "mock"
    embedding_model: str = "mock-hash-embedding-v1"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: SecretStr | None = Field(default=None, repr=False)
    embedding_dimensions: int = Field(default=64, ge=2, le=4096)
    embedding_batch_size: int = Field(default=32, ge=1, le=2048)
    embedding_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    embedding_max_retries: int = Field(default=2, ge=0, le=10)
    vector_distance: Literal["cosine"] = "cosine"
    retrieval_top_k: int = Field(default=20, ge=1, le=100)
    retrieval_max_top_k: int = Field(default=100, ge=1, le=500)
    retrieval_max_context_chars: int = Field(default=16_000, ge=500, le=100_000)
    hybrid_keyword_weight: float = Field(default=0.20, ge=0, le=1)
    hybrid_vector_weight: float = Field(default=0.35, ge=0, le=1)
    hybrid_fact_weight: float = Field(default=0.25, ge=0, le=1)
    hybrid_graph_weight: float = Field(default=0.20, ge=0, le=1)
    retrieval_debug: bool = False
    mock_workflow_scenario: Literal["pass", "improve", "stagnate"] = "improve"
    mock_critic_scenario: Literal["normal", "death", "outline", "poor", "conflict"] = "normal"
    mock_mode: bool = True
    auto_migrate: bool = False
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65_535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["text", "json"] = "text"
    allowed_origins: tuple[str, ...] = ()
    cors_allow_credentials: bool = False
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
    database_wait_attempts: int = Field(default=30, ge=1, le=300)
    database_wait_interval_seconds: float = Field(default=1.0, ge=0, le=30)

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
        if self.retrieval_top_k > self.retrieval_max_top_k:
            raise ConfigurationError("Default retrieval top_k cannot exceed its maximum")
        if self.embedding_dimensions != 64:
            raise ConfigurationError("Embedding dimensions must match the database dimension 64")
        hybrid_total = sum(
            (
                self.hybrid_keyword_weight,
                self.hybrid_vector_weight,
                self.hybrid_fact_weight,
                self.hybrid_graph_weight,
            )
        )
        if abs(hybrid_total - 1.0) > 1e-9:
            raise ConfigurationError("Hybrid retrieval weights must sum to 1")
        database_url = make_url(normalize_database_url(self.database_url))
        if self.environment == "production" and database_url.get_backend_name() != "postgresql":
            raise ConfigurationError("Production must explicitly configure a PostgreSQL database")
        if self.environment == "production" and database_url.password == "storyforge-dev-only":
            raise ConfigurationError("Production cannot use the documented development password")
        if self.environment == "production" and self.llm_provider == "mock":
            raise ConfigurationError("Production must explicitly configure a non-mock provider")
        if self.environment == "production" and self.mock_mode:
            raise ConfigurationError("Production must explicitly disable mock mode")
        if self.environment == "production" and self.embedding_provider == "mock":
            raise ConfigurationError(
                "Production must explicitly configure a non-mock embedding provider"
            )
        if self.llm_provider == "mock" and not self.mock_mode:
            raise ConfigurationError("Mock provider requires STORYFORGE_MOCK_MODE=true")
        if self.cors_allow_credentials and "*" in self.allowed_origins:
            raise ConfigurationError("Credentialed CORS cannot allow every origin")
        if self.llm_provider == "openai-compatible":
            key = self.llm_api_key.get_secret_value() if self.llm_api_key is not None else ""
            if not key:
                raise ConfigurationError("OpenAI-compatible provider requires an API key")
            if not self.llm_model or self.llm_model.startswith("replace-with"):
                raise ConfigurationError("OpenAI-compatible provider requires a real model name")
        if self.embedding_provider == "openai-compatible":
            key = (
                self.embedding_api_key.get_secret_value()
                if self.embedding_api_key is not None
                else ""
            )
            if not key:
                raise ConfigurationError("OpenAI-compatible embedding provider requires an API key")
            if not self.embedding_model or self.embedding_model.startswith("replace-with"):
                raise ConfigurationError(
                    "OpenAI-compatible embedding provider requires a real model name"
                )
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

        def first(names: tuple[str, ...], default: str) -> str:
            for name in names:
                current = values.get(name)
                if current is not None:
                    return current
            return default

        key_value = value("LLM_API_KEY", "OPENAI_API_KEY", "")
        embedding_key_value = value("EMBEDDING_API_KEY", None, "")
        checkpoint = value("CHECKPOINT_PATH", None, "")
        environment_value = value("ENVIRONMENT", None, "development")
        if (
            environment_value == "test"
            and "STORYFORGE_DATABASE_URL" not in values
            and "DATABASE_URL" not in values
        ):
            raise ConfigurationError("Test environment requires an explicit test database URL")
        database_value = value("DATABASE_URL", "DATABASE_URL", "sqlite:///./storyforge.db")
        allowed_origins = tuple(
            item.strip() for item in value("ALLOWED_ORIGINS", None, "").split(",") if item.strip()
        )
        try:
            return cls(
                environment=cast(
                    Literal["development", "test", "production"],
                    environment_value,
                ),
                database_url=database_value,
                llm_provider=cast(
                    Literal["mock", "openai-compatible"],
                    value("LLM_PROVIDER", None, "mock"),
                ),
                llm_model=value("LLM_MODEL", "OPENAI_MODEL", "mock-storyforge-v1"),
                llm_api_base_url=first(
                    (
                        "STORYFORGE_LLM_BASE_URL",
                        "STORYFORGE_LLM_API_BASE_URL",
                        "OPENAI_BASE_URL",
                    ),
                    "https://api.openai.com/v1",
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
                embedding_provider=cast(
                    Literal["mock", "openai-compatible"],
                    value("EMBEDDING_PROVIDER", None, "mock"),
                ),
                embedding_model=value("EMBEDDING_MODEL", None, "mock-hash-embedding-v1"),
                embedding_base_url=value("EMBEDDING_BASE_URL", None, "https://api.openai.com/v1"),
                embedding_api_key=(SecretStr(embedding_key_value) if embedding_key_value else None),
                embedding_dimensions=int(value("EMBEDDING_DIMENSIONS", None, "64")),
                embedding_batch_size=int(value("EMBEDDING_BATCH_SIZE", None, "32")),
                embedding_timeout_seconds=float(value("EMBEDDING_TIMEOUT", None, "30")),
                embedding_max_retries=int(value("EMBEDDING_MAX_RETRIES", None, "2")),
                vector_distance=cast(Literal["cosine"], value("VECTOR_DISTANCE", None, "cosine")),
                retrieval_top_k=int(value("RETRIEVAL_TOP_K", None, "20")),
                retrieval_max_top_k=int(value("RETRIEVAL_MAX_TOP_K", None, "100")),
                retrieval_max_context_chars=int(
                    value("RETRIEVAL_MAX_CONTEXT_CHARS", None, "16000")
                ),
                hybrid_keyword_weight=float(value("HYBRID_KEYWORD_WEIGHT", None, "0.20")),
                hybrid_vector_weight=float(value("HYBRID_VECTOR_WEIGHT", None, "0.35")),
                hybrid_fact_weight=float(value("HYBRID_FACT_WEIGHT", None, "0.25")),
                hybrid_graph_weight=float(value("HYBRID_GRAPH_WEIGHT", None, "0.20")),
                retrieval_debug=_boolean(
                    value("RETRIEVAL_DEBUG", None, "false"),
                    name="STORYFORGE_RETRIEVAL_DEBUG",
                ),
                mock_workflow_scenario=cast(
                    Literal["pass", "improve", "stagnate"],
                    value("MOCK_WORKFLOW_SCENARIO", None, "improve"),
                ),
                mock_critic_scenario=cast(
                    Literal["normal", "death", "outline", "poor", "conflict"],
                    value("MOCK_CRITIC_SCENARIO", None, "normal"),
                ),
                mock_mode=_boolean(
                    value(
                        "MOCK_MODE",
                        None,
                        "false" if environment_value == "production" else "true",
                    ),
                    name="STORYFORGE_MOCK_MODE",
                ),
                auto_migrate=_boolean(
                    value("AUTO_MIGRATE", None, "false"),
                    name="STORYFORGE_AUTO_MIGRATE",
                ),
                api_host=value("API_HOST", None, "127.0.0.1"),
                api_port=int(value("API_PORT", None, "8000")),
                log_level=cast(
                    Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                    value("LOG_LEVEL", None, "INFO").upper(),
                ),
                log_format=cast(
                    Literal["text", "json"],
                    value(
                        "LOG_FORMAT",
                        None,
                        "json" if environment_value == "production" else "text",
                    ).lower(),
                ),
                allowed_origins=allowed_origins,
                cors_allow_credentials=_boolean(
                    value("CORS_ALLOW_CREDENTIALS", None, "false"),
                    name="STORYFORGE_CORS_ALLOW_CREDENTIALS",
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
                max_request_body_bytes=int(
                    first(
                        (
                            "STORYFORGE_REQUEST_BODY_LIMIT",
                            "STORYFORGE_MAX_REQUEST_BODY_BYTES",
                        ),
                        "1048576",
                    )
                ),
                max_chapter_content_chars=int(value("MAX_CHAPTER_CONTENT_CHARS", None, "500000")),
                max_diff_chars=int(value("MAX_DIFF_CHARS", None, "50000")),
                checkpoint_path=Path(checkpoint) if checkpoint else None,
                enable_http_logging=_boolean(
                    value("ENABLE_HTTP_LOGGING", None, "true"),
                    name="STORYFORGE_ENABLE_HTTP_LOGGING",
                ),
                database_wait_attempts=int(value("DATABASE_WAIT_ATTEMPTS", None, "30")),
                database_wait_interval_seconds=float(
                    value("DATABASE_WAIT_INTERVAL_SECONDS", None, "1")
                ),
            )
        except ValueError as exc:
            raise ConfigurationError("StoryForge numeric or enum settings are invalid") from exc
