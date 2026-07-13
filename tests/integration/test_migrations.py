"""Alembic migration integration tests against temporary SQLite."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from storyforge.database import create_database_engine
from storyforge.models import Base

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
