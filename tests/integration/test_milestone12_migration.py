"""Cold and M11-to-M12 migration verification."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from storyforge.database import create_database_engine
from storyforge.migrations import MIGRATION_HEAD

ROOT = Path(__file__).resolve().parents[2]
M11_HEAD = "b61d3f7a2c10"


def test_m11_database_upgrades_to_single_m12_head(tmp_path: Path) -> None:
    database = tmp_path / "m11-to-m12.sqlite3"
    url = f"sqlite:///{database.as_posix()}"
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    engine = create_database_engine(url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, M11_HEAD)
            connection.execute(
                text(
                    "INSERT INTO jobs (job_type, queue_name, status, priority, "
                    "idempotency_key, payload, payload_schema_version, result, "
                    "result_schema_version, progress, attempt, max_attempts, available_at, "
                    "correlation_id, created_at, updated_at) VALUES "
                    "('generate_plan','storyforge.planning','succeeded',5,'legacy-job','{}',1,"
                    "'{}',1,100,1,3,CURRENT_TIMESTAMP,'legacy',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO job_events (job_id, sequence, event_type, status, progress, "
                    "message_code, message, attempt, created_at) VALUES "
                    "(1,1,'job_succeeded','succeeded',100,'legacy','legacy event',1,CURRENT_TIMESTAMP)"
                )
            )
            command.upgrade(config, "head")
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version")) == MIGRATION_HEAD
            )
            assert connection.scalar(text("SELECT event_sequence FROM jobs WHERE id=1")) == 1
        tables = set(inspect(engine).get_table_names())
        assert {
            "book_runs",
            "book_snapshots",
            "timeline_events",
            "character_arc_points",
            "character_knowledge",
            "relationship_history",
            "book_evaluations",
            "book_revision_plans",
            "book_revision_tasks",
            "chapter_transition_evaluations",
        }.issubset(tables)
    finally:
        engine.dispose()


def test_fresh_m12_schema_matches_metadata(tmp_path: Path) -> None:
    database = tmp_path / "m12-fresh.sqlite3"
    url = f"sqlite:///{database.as_posix()}"
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_database_engine(url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            command.check(config)
    finally:
        engine.dispose()
