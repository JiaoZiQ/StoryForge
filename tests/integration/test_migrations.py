"""Alembic migration integration tests against temporary SQLite."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from tests._factories import create_story_graph

from storyforge.database import create_database_engine, create_session_factory
from storyforge.models import Base, Project

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_initial_migration_upgrade_matches_metadata_and_downgrades(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first migration should build the model schema and cleanly revert it."""
    database_path = tmp_path / "migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))

    command.upgrade(alembic_config, "head")

    engine = create_database_engine(database_url)
    inspector = inspect(engine)
    migrated_tables = set(inspector.get_table_names())
    model_tables = set(Base.metadata.tables)
    assert model_tables <= migrated_tables

    for table_name, table in Base.metadata.tables.items():
        migrated_columns = {column["name"] for column in inspector.get_columns(table_name)}
        assert {column.name for column in table.columns} == migrated_columns

    command.check(alembic_config)
    engine.dispose()

    command.downgrade(alembic_config, "base")

    downgraded_engine = create_database_engine(database_url)
    try:
        downgraded_tables = set(inspect(downgraded_engine).get_table_names())
        assert model_tables.isdisjoint(downgraded_tables)
    finally:
        downgraded_engine.dispose()


def test_milestone7_data_upgrades_to_memory_schema_without_old_migration_edits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "m7-to-m8.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(config, "c7d4e1a2b9f0")
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    with session_factory.begin() as session:
        project_id = create_story_graph(session).project.id
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_database_engine(database_url)
    inspector = inspect(engine)
    assert {
        "memory_chunks",
        "memory_index_records",
        "graph_entities",
        "graph_relations",
    } <= set(inspector.get_table_names())
    with create_session_factory(engine)() as session:
        assert session.get(Project, project_id) is not None
    engine.dispose()

    command.downgrade(config, "c7d4e1a2b9f0")
    engine = create_database_engine(database_url)
    inspector = inspect(engine)
    assert "projects" in inspector.get_table_names()
    assert "memory_chunks" not in inspector.get_table_names()
    engine.dispose()


def test_milestone3_migration_backfills_existing_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M3 must upgrade real M1 rows, not only initialize an empty database."""
    database_path = tmp_path / "existing.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(alembic_config, "3d5c121d94ea")

    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects "
                "(id, title, genre, premise, target_chapters, "
                "target_words_per_chapter, status) "
                "VALUES (1, 'Existing', 'Mystery', 'Old data', 3, 1000, 'draft')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO chapters "
                "(id, project_id, chapter_number, title, outline, content, status, version) "
                "VALUES (1, 1, 1, 'One', 'Outline', '', 'planned', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO characters "
                "(id, project_id, name, role, description, goals, personality, "
                "speech_style, current_state, secrets) "
                "VALUES (1, 1, 'Mara', 'lead', 'desc', '[]', 'calm', 'brief', 'home', '[]')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO facts "
                "(id, project_id, chapter_id, subject, predicate, object, "
                "valid_from_chapter, confidence, source_quote) "
                "VALUES (1, 1, 1, 'Mara', 'is', 'home', 1, 1.0, 'Mara is home')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO foreshadowings "
                "(id, project_id, setup_chapter, expected_payoff_chapter, description, status) "
                "VALUES (1, 1, 1, 2, 'A key', 'planned')"
            )
        )
    engine.dispose()

    command.upgrade(alembic_config, "head")
    upgraded = create_database_engine(database_url)
    with upgraded.connect() as connection:
        assert connection.execute(
            text("SELECT language, themes FROM projects WHERE id=1")
        ).one() == ("zh-CN", "[]")
        assert connection.execute(
            text("SELECT objective, outline_metadata FROM chapters WHERE id=1")
        ).one() == ("", "{}")
        assert (
            connection.scalar(text("SELECT personality_traits FROM characters WHERE id=1")) == "[]"
        )
        assert connection.scalar(text("SELECT fact_type FROM facts WHERE id=1")) == "event"
        assert (
            connection.scalar(text("SELECT importance FROM foreshadowings WHERE id=1")) == "medium"
        )
    upgraded.dispose()
    command.downgrade(alembic_config, "base")
