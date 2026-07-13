"""Shared isolated SQLite fixtures."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from storyforge.database import create_database_engine, create_session_factory
from storyforge.models import Base


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    """Create a new in-memory database with foreign keys enabled."""
    engine = create_database_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def session(db_engine: Engine) -> Iterator[Session]:
    """Provide one session that is rolled back and closed after each test."""
    session_factory = create_session_factory(db_engine)
    database_session = session_factory()
    try:
        yield database_session
    finally:
        database_session.rollback()
        database_session.close()
