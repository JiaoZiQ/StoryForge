"""Milestone 5 data upgrades into the API metadata schema."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from storyforge.database import create_database_engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m6_migration_backfills_project_metadata_and_downgrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "existing-m5.sqlite3"
    database_url = f"sqlite:///{database.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(config, "69c75316dd7e")
    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects "
                "(id, title, genre, premise, target_chapters, target_words_per_chapter, "
                "language, themes, status, created_at, updated_at) VALUES "
                "(1, 'Existing M5', 'Mystery', 'Premise', 3, 300, 'en', '[]', "
                "'draft', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()

    command.upgrade(config, "head")
    upgraded = create_database_engine(database_url)
    inspector = inspect(upgraded)
    assert "additional_requirements" in {
        column["name"] for column in inspector.get_columns("projects")
    }
    assert {"mechanical_metrics", "critic_dimensions"} <= {
        column["name"] for column in inspector.get_columns("evaluations")
    }
    assert "resolution_note" in {
        column["name"] for column in inspector.get_columns("consistency_conflicts")
    }
    with upgraded.connect() as connection:
        assert connection.execute(
            text("SELECT status, additional_requirements FROM projects WHERE id=1")
        ).one() == ("draft", "")
    upgraded.dispose()

    command.downgrade(config, "69c75316dd7e")
    downgraded = create_database_engine(database_url)
    assert "additional_requirements" not in {
        column["name"] for column in inspect(downgraded).get_columns("projects")
    }
    downgraded.dispose()
