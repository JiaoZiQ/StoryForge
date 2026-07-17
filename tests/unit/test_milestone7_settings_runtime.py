"""Milestone 7 configuration, startup, and structured-log safety tests."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from storyforge.exceptions import ConfigurationError
from storyforge.logging_config import JsonLogFormatter, SensitiveDataFilter, redact_sensitive
from storyforge.runtime import DatabaseWaitError, wait_for_database, wait_for_db_main
from storyforge.settings import Settings


def test_development_defaults_are_explicit_sqlite_mock() -> None:
    settings = Settings.from_env({})
    assert settings.environment == "development"
    assert settings.database_url == "sqlite:///./storyforge.db"
    assert settings.llm_provider == "mock"
    assert settings.mock_mode is True
    assert settings.auto_migrate is False
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000


def test_test_environment_requires_explicit_database() -> None:
    with pytest.raises(ConfigurationError, match="explicit test database"):
        Settings.from_env({"STORYFORGE_ENVIRONMENT": "test"})


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({}, "PostgreSQL"),
        (
            {"database_url": "postgresql://user:secret@db/storyforge"},
            "non-mock provider",
        ),
        (
            {
                "database_url": "postgresql://user:storyforge-dev-only@db/storyforge",
                "llm_provider": "openai-compatible",
                "llm_model": "real-model",
                "llm_api_key": "secret",
                "mock_mode": False,
            },
            "development password",
        ),
    ],
)
def test_production_rejects_unsafe_fallbacks(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        Settings(environment="production", **overrides)


def test_production_accepts_explicit_postgres_and_real_provider() -> None:
    settings = Settings(
        environment="production",
        database_url="postgresql://user:unique-secret@db/storyforge",
        llm_provider="openai-compatible",
        llm_model="structured-model",
        llm_api_key="key-value",
        mock_mode=False,
        allowed_origins=("https://example.test",),
        cors_allow_credentials=True,
    )
    assert settings.log_level == "INFO"
    assert "unique-secret" not in repr(settings)
    assert "key-value" not in repr(settings)


def test_credentialed_cors_rejects_wildcard() -> None:
    with pytest.raises(ConfigurationError, match="CORS"):
        Settings(allowed_origins=("*",), cors_allow_credentials=True)


def test_canonical_prefixed_environment_variables_are_read() -> None:
    settings = Settings.from_env(
        {
            "STORYFORGE_ENVIRONMENT": "test",
            "STORYFORGE_DATABASE_URL": "sqlite:///:memory:",
            "STORYFORGE_LLM_BASE_URL": "https://models.example.test/v1",
            "STORYFORGE_API_HOST": "0.0.0.0",
            "STORYFORGE_API_PORT": "9000",
            "STORYFORGE_LOG_FORMAT": "json",
            "STORYFORGE_ALLOWED_ORIGINS": "https://one.test, https://two.test",
            "STORYFORGE_REQUEST_BODY_LIMIT": "2048",
            "STORYFORGE_DATABASE_WAIT_ATTEMPTS": "5",
            "STORYFORGE_DATABASE_WAIT_INTERVAL_SECONDS": "0.25",
        }
    )
    assert settings.llm_api_base_url == "https://models.example.test/v1"
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 9000
    assert settings.log_format == "json"
    assert settings.allowed_origins == ("https://one.test", "https://two.test")
    assert settings.max_request_body_bytes == 2048
    assert settings.database_wait_attempts == 5
    assert settings.database_wait_interval_seconds == 0.25


def test_database_wait_retries_without_leaking_url(caplog: pytest.LogCaptureFixture) -> None:
    attempts = 0

    def probe(_: str) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("postgresql://user:password-value@db/storyforge")

    waits: list[float] = []
    with caplog.at_level(logging.INFO):
        wait_for_database(
            "postgresql://user:password-value@db/storyforge",
            attempts=3,
            interval_seconds=0.5,
            probe=probe,
            sleeper=waits.append,
        )
    assert attempts == 3
    assert waits == [0.5, 0.5]
    assert "password-value" not in caplog.text


def test_database_wait_timeout_is_bounded_and_sanitized() -> None:
    probes: list[str] = []

    def fail(url: str) -> None:
        probes.append(url)
        raise RuntimeError("connection refused")

    with pytest.raises(DatabaseWaitError, match="after 2 attempts") as caught:
        wait_for_database(
            "postgresql://user:password-value@db/storyforge",
            attempts=2,
            interval_seconds=0,
            probe=fail,
            sleeper=lambda _: None,
        )
    assert len(probes) == 2
    assert "password-value" not in str(caught.value)


def test_database_wait_entrypoint_returns_nonzero_without_traceback_or_secret(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    settings = Settings(database_url="postgresql://user:password-value@db/storyforge")
    monkeypatch.setattr("storyforge.runtime.Settings.from_env", lambda *_: settings)
    monkeypatch.setattr("storyforge.runtime.configure_logging", lambda *_args, **_kwargs: None)

    def fail(*_: object, **__: object) -> None:
        raise DatabaseWaitError("password-value must not be rendered")

    monkeypatch.setattr("storyforge.runtime.wait_for_database", fail)
    with caplog.at_level(logging.ERROR):
        assert wait_for_db_main() == 1
    assert "password-value" not in caplog.text
    assert "Traceback" not in caplog.text
    assert "DatabaseWaitError" in caplog.text


def test_json_logging_is_valid_structured_and_redacted() -> None:
    record = logging.LogRecord(
        "storyforge.test",
        logging.INFO,
        str(Path(__file__)),
        1,
        "Authorization=Bearer secret-token password=database-secret",
        (),
        None,
    )
    record.request_id = "request-1"
    record.method = "GET"
    record.path = "/api/v1/ready"
    record.status = 200
    record.duration_ms = 4
    assert SensitiveDataFilter().filter(record)
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["request_id"] == "request-1"
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/v1/ready"
    assert payload["status"] == 200
    serialized = json.dumps(payload)
    assert "secret-token" not in serialized
    assert "database-secret" not in serialized
    assert "[REDACTED]" in serialized


def test_database_url_redaction_handles_psycopg_urls() -> None:
    rendered = redact_sensitive(
        "failed postgresql+psycopg://storyforge:database-secret@postgres:5432/storyforge"
    )
    assert "database-secret" not in rendered
    assert "[REDACTED]" in rendered
