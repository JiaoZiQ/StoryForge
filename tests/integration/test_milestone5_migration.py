"""Milestone 4 data upgrades safely into version-scoped Milestone 5 storage."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from storyforge.database import create_database_engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m5_migration_backfills_versions_facts_and_evaluations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "existing-m4.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(config, "ad6fd0f94186")
    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects "
                "(id, title, genre, premise, target_chapters, target_words_per_chapter, "
                "language, themes, status, created_at, updated_at) VALUES "
                "(1, 'Existing M4', 'Mystery', 'Premise', 3, 300, 'en', '[]', "
                "'generating', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO chapters "
                "(id, project_id, chapter_number, title, outline, objective, "
                "outline_metadata, content, summary, status, version, generation_metadata, "
                "created_at, updated_at) VALUES "
                "(1, 1, 1, 'One', 'Outline', 'Objective', '{}', 'Legacy body', "
                "'Legacy summary', 'evaluated_passed', 1, '{}', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO facts "
                "(id, project_id, chapter_id, subject, predicate, object, fact_type, "
                "valid_from_chapter, confidence, source_quote) VALUES "
                "(1, 1, 1, 'Mara', 'carries', 'brass key', 'possession', 1, 0.99, "
                "'Mara lifted the brass key')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO evaluations "
                "(id, project_id, chapter_id, evaluation_version, evaluator, overall_score, consistency_score, "
                "prose_score, character_score, plot_score, issues, suggestions, created_at) "
                "VALUES (1, 1, 1, 1, 'legacy', 8, 8, 8, 8, 8, '[]', '[]', CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()

    command.upgrade(config, "head")
    upgraded = create_database_engine(database_url)
    with upgraded.connect() as connection:
        chapter = connection.execute(
            text("SELECT current_version_id, accepted_version_id FROM chapters WHERE id=1")
        ).one()
        assert chapter[0] is not None and chapter[0] == chapter[1]
        version = connection.execute(
            text("SELECT id, status, source, content FROM chapter_versions WHERE chapter_id=1")
        ).one()
        assert version == (chapter[0], "accepted", "legacy", "Legacy body")
        fact = connection.execute(
            text("SELECT chapter_version_id, status, normalized_hash FROM facts WHERE id=1")
        ).one()
        assert fact[0] == version[0]
        assert fact[1] == "accepted"
        assert len(fact[2]) == 64
        evaluation = connection.execute(
            text(
                "SELECT chapter_version_id, workflow_run_id, idempotency_key "
                "FROM evaluations WHERE id=1"
            )
        ).one()
        assert evaluation == (version[0], None, None)
    upgraded.dispose()

    command.downgrade(config, "ad6fd0f94186")
    downgraded = create_database_engine(database_url)
    inspector = inspect(downgraded)
    assert "chapter_version_id" not in {item["name"] for item in inspector.get_columns("facts")}
    assert downgraded.connect().scalar(text("SELECT content FROM chapters WHERE id=1")) == (
        "Legacy body"
    )
    downgraded.dispose()
