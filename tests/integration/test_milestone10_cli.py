"""Milestone 10 CLI JSON, confirmation, and secret-safe smoke gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from storyforge.cli.app import main
from storyforge.database import create_database_engine, create_session_factory
from storyforge.schemas.domain import ProjectCreate
from storyforge.services import ProjectService

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_governance_cli_outputs_parseable_json_and_requires_confirmation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "m10-cli.sqlite3"
    database_url = f"sqlite:///{database.as_posix()}"
    monkeypatch.setenv("STORYFORGE_DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("STORYFORGE_ENVIRONMENT", "test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    engine = create_database_engine(database_url)
    try:
        project = ProjectService(create_session_factory(engine)).create(
            ProjectCreate(
                title="CLI governance",
                genre="test",
                premise="safe cli",
                target_chapters=1,
                target_words_per_chapter=100,
            )
        )
    finally:
        engine.dispose()

    assert main(["provider", "list", "--output", "json"]) == 0
    providers = json.loads(capsys.readouterr().out)
    assert len(providers) == 3
    assert "api_key" not in json.dumps(providers)
    assert main(["provider", "health", "--output", "json"]) == 0
    assert all(item["circuit_status"] == "closed" for item in json.loads(capsys.readouterr().out))

    assert (
        main(
            [
                "budget",
                "set",
                "--project-id",
                str(project.id),
                "--soft-limit",
                "1.00000001",
                "--hard-limit",
                "2.00000002",
                "--output",
                "json",
            ]
        )
        == 2
    )
    error = json.loads(capsys.readouterr().err)
    assert error["error"] == "validation_error"
    assert (
        main(
            [
                "budget",
                "set",
                "--project-id",
                str(project.id),
                "--soft-limit",
                "1.00000001",
                "--hard-limit",
                "2.00000002",
                "--yes",
                "--output",
                "json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["hard_limit"] == "2.00000002"
    assert (
        main(
            [
                "model-profile",
                "set",
                "--project-id",
                str(project.id),
                "--profile",
                "balanced",
                "--yes",
                "--output",
                "json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "privacy-policy",
                "set",
                "--project-id",
                str(project.id),
                "--policy",
                "strict",
                "--yes",
                "--output",
                "json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["privacy_policy"] == "strict"
    assert (
        main(
            [
                "usage",
                "summary",
                "--project-id",
                str(project.id),
                "--output",
                "json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["calls"] == 0


def test_real_smoke_is_disabled_and_never_prints_credentials(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-value-never-print")
    monkeypatch.setenv("STORYFORGE_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("OPENAI_MODEL", "registered-test-model")
    monkeypatch.setenv("STORYFORGE_ENABLE_REAL_PROVIDER_TESTS", "false")
    assert (
        main(
            [
                "provider",
                "smoke-test",
                "--provider",
                "openai-compatible",
                "--output",
                "json",
            ]
        )
        == 5
    )
    rendered = capsys.readouterr().err
    assert "sk-test-value-never-print" not in rendered
    assert "provider_unavailable" in rendered
