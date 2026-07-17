"""Readiness remains false until the database reaches the exact migration head."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from storyforge.api.app import create_app
from storyforge.settings import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_readiness_is_503_for_reachable_but_outdated_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "outdated.sqlite3"
    database_url = f"sqlite:///{database.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(str(ROOT / "alembic.ini")), "f2a6c8d91b04")
    settings = Settings(environment="test", database_url=database_url)

    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        ready = client.get("/api/v1/ready")

    assert ready.status_code == 503
    assert ready.json()["error"] == "database_not_ready"
    assert "migration" in ready.json()["message"].casefold()
