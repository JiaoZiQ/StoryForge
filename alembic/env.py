"""Alembic environment bound to StoryForge settings and model metadata."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, make_url

from storyforge.database import create_database_engine, get_database_url
from storyforge.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without opening a database connection."""
    database_url = get_database_url()
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=make_url(database_url).get_backend_name() == "sqlite",
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    """Configure and execute migrations on one connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a supplied or newly created connection."""
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        if not isinstance(supplied_connection, Connection):
            raise TypeError("Alembic connection attribute must be a SQLAlchemy Connection")
        _run_migrations(supplied_connection)
        return

    engine = create_database_engine(get_database_url())
    with engine.connect() as connection:
        _run_migrations(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
