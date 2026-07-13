"""Milestone-four migration compatibility tests."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from storyforge.database import create_database_engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m4_migration_upgrades_existing_m3_evaluations_and_versions_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "existing-m3.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(config, "b550a962dc62")

    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects "
                "(id, title, genre, premise, target_chapters, target_words_per_chapter, "
                "language, themes, status, created_at, updated_at) "
                "VALUES (1, 'Existing M3', 'Mystery', 'Premise', 3, 300, 'zh-CN', '[]', "
                "'generating', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO chapters "
                "(id, project_id, chapter_number, title, outline, objective, "
                "outline_metadata, content, summary, status, version, generation_metadata, "
                "created_at, updated_at) VALUES "
                "(1, 1, 1, 'One', 'Outline', 'Objective', '{}', 'Body', 'Summary', "
                "'generated', 1, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO characters "
                "(id, project_id, name, role, description, goals, personality, "
                "personality_traits, speech_style, current_state, secrets) VALUES "
                "(1, 1, 'Mara', 'lead', 'desc', '[]', 'calm', '[]', 'brief', 'active', '[]')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO story_rules "
                "(id, project_id, category, statement, source, active) VALUES "
                "(1, 1, 'world', 'A rule', 'planner', 1)"
            )
        )
        for evaluation_id in (1, 2):
            connection.execute(
                text(
                    "INSERT INTO evaluations "
                    "(id, project_id, chapter_id, evaluator, overall_score, consistency_score, "
                    "prose_score, character_score, plot_score, issues, suggestions, created_at) "
                    "VALUES (:id, 1, 1, 'legacy', 8, 8, 8, 8, 8, '[]', '[]', "
                    "CURRENT_TIMESTAMP)"
                ),
                {"id": evaluation_id},
            )
    engine.dispose()

    command.upgrade(config, "head")
    upgraded = create_database_engine(database_url)
    with upgraded.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT evaluation_version, status, provider, raw_scores, blocking_reasons "
                "FROM evaluations ORDER BY id"
            )
        ).all()
        assert rows == [
            (1, "completed", "legacy", "{}", "[]"),
            (2, "completed", "legacy", "{}", "[]"),
        ]
        assert connection.scalar(text("SELECT knowledge FROM characters WHERE id=1")) == "[]"
        assert (
            connection.scalar(text("SELECT structured_metadata FROM story_rules WHERE id=1"))
            == "{}"
        )
    upgraded.dispose()

    command.downgrade(config, "base")
