"""Unit tests for engine and transaction configuration."""

import pytest
from sqlalchemy import Engine, func, select, text
from tests._factories import make_project

from storyforge.database import (
    DEFAULT_DATABASE_URL,
    create_database_engine,
    create_session_factory,
    get_database_url,
    normalize_database_url,
    transactional_session,
)
from storyforge.models import Project


def test_database_url_defaults_to_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local development should require no external database service."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_database_url() == DEFAULT_DATABASE_URL


@pytest.mark.parametrize("scheme", ["postgres://", "postgresql://"])
def test_driverless_postgresql_urls_select_psycopg3(scheme: str) -> None:
    """Common PostgreSQL URLs should use the installed Psycopg 3 dialect."""
    normalized = normalize_database_url(f"{scheme}user@localhost/storyforge")
    assert normalized == "postgresql+psycopg://user@localhost/storyforge"


def test_empty_database_url_is_rejected() -> None:
    """An explicitly empty DATABASE_URL should fail before engine creation."""
    with pytest.raises(ValueError, match="must not be empty"):
        normalize_database_url("   ")


def test_postgresql_engine_uses_psycopg_without_connecting() -> None:
    """Creating an optional PostgreSQL engine should select Psycopg 3."""
    engine = create_database_engine("postgresql://user@localhost/storyforge")
    try:
        assert engine.url.drivername == "postgresql+psycopg"
    finally:
        engine.dispose()


def test_sqlite_engine_enables_foreign_keys(db_engine: Engine) -> None:
    """SQLite must enforce the same cascade constraints expected in production."""
    with db_engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1


def test_transactional_session_commits_and_rolls_back(db_engine: Engine) -> None:
    """The session context should commit success and roll back exceptions atomically."""
    session_factory = create_session_factory(db_engine)

    with transactional_session(session_factory) as session:
        session.add(make_project(title="Committed"))

    with pytest.raises(RuntimeError, match="abort transaction"):
        with transactional_session(session_factory) as session:
            session.add(make_project(title="Rolled back"))
            raise RuntimeError("abort transaction")

    with session_factory() as session:
        titles = list(session.scalars(select(Project.title).order_by(Project.id)))
        count = session.scalar(select(func.count()).select_from(Project))

    assert titles == ["Committed"]
    assert count == 1
