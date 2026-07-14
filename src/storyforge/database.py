"""Database URL, engine, and transaction-scoped session configuration."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event, make_url
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool

DEFAULT_DATABASE_URL = "sqlite:///./storyforge.db"

SessionFactory = sessionmaker[Session]


def normalize_database_url(database_url: str) -> str:
    """Select Psycopg 3 for driverless PostgreSQL URLs."""
    value = database_url.strip()
    if not value:
        raise ValueError("DATABASE_URL must not be empty")
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def get_database_url() -> str:
    """Read the database URL dynamically so tests and migrations can override it."""
    return normalize_database_url(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))


def _enable_sqlite_foreign_keys(
    dbapi_connection: DBAPIConnection,
    _: ConnectionPoolEntry,
) -> None:
    """Enable SQLite foreign-key enforcement for every new DBAPI connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_database_engine(
    database_url: str | None = None,
    *,
    echo: bool = False,
) -> Engine:
    """Create an engine for SQLite or a DATABASE_URL-selected PostgreSQL database."""
    normalized_url = normalize_database_url(database_url or get_database_url())
    url = make_url(normalized_url)
    options: dict[str, Any] = {
        "echo": echo,
        "pool_pre_ping": True,
    }

    if url.get_backend_name() == "sqlite":
        options["connect_args"] = {"check_same_thread": False}
        if url.database in (None, "", ":memory:"):
            options["poolclass"] = StaticPool

    engine = create_engine(url, **options)
    if url.get_backend_name() == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def create_session_factory(engine: Engine) -> SessionFactory:
    """Create sessions that keep loaded objects usable after commits."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def transactional_session(session_factory: SessionFactory) -> Iterator[Session]:
    """Commit atomically on success and roll back automatically on errors."""
    with session_factory.begin() as session:
        yield session
