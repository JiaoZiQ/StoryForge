"""Deployment entry points for database waiting, migrations, and Uvicorn."""

from __future__ import annotations

import logging
import os
import time
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from uuid import uuid4

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from storyforge.database import (
    DEFAULT_DATABASE_URL,
    create_database_engine,
    create_session_factory,
    normalize_database_url,
)
from storyforge.exceptions import ConfigurationError, StoryForgeError
from storyforge.logging_config import configure_logging
from storyforge.settings import Settings

logger = logging.getLogger(__name__)


class DatabaseWaitError(StoryForgeError):
    """Raised when a database does not become reachable within the configured budget."""


def runtime_database_url(environ: Mapping[str, str] | None = None) -> str:
    """Read the application-prefixed URL while retaining Alembic compatibility."""
    values = os.environ if environ is None else environ
    return normalize_database_url(
        values.get("STORYFORGE_DATABASE_URL") or values.get("DATABASE_URL") or DEFAULT_DATABASE_URL
    )


def probe_database(database_url: str) -> None:
    """Open one short connection and execute a portable liveness query."""
    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()


def wait_for_database(
    database_url: str,
    *,
    attempts: int,
    interval_seconds: float,
    probe: Callable[[str], None] = probe_database,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    """Retry a real connection with bounded, configurable waiting."""
    if attempts < 1:
        raise ValueError("attempts must be positive")
    if interval_seconds < 0:
        raise ValueError("interval_seconds cannot be negative")
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            probe(database_url)
            logger.info("database_ready attempt=%s", attempt)
            return
        except Exception as exc:  # the final public error is deliberately sanitized
            last_error = exc
            if attempt < attempts:
                logger.warning(
                    "database_wait_retry attempt=%s max_attempts=%s exception_type=%s",
                    attempt,
                    attempts,
                    type(exc).__name__,
                )
                sleeper(interval_seconds)
    raise DatabaseWaitError(
        f"Database did not become ready after {attempts} attempts"
    ) from last_error


def run_migrations(database_url: str, *, config_path: Path | None = None) -> None:
    """Upgrade the configured database without printing its credential-bearing URL."""
    path = config_path or Path(os.getenv("STORYFORGE_ALEMBIC_CONFIG", "alembic.ini"))
    if not path.is_file():
        raise ConfigurationError("Alembic configuration file was not found")
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(Config(str(path)), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def wait_for_db_main() -> int:
    """Console entry point used by operators and container diagnostics."""
    try:
        settings = Settings.from_env()
        configure_logging(settings, force=True)
        wait_for_database(
            settings.database_url,
            attempts=settings.database_wait_attempts,
            interval_seconds=settings.database_wait_interval_seconds,
        )
    except Exception as exc:
        return _deployment_failure("database_wait", exc)
    return 0


def migrate_main() -> int:
    """Wait for the database and apply all Alembic migrations exactly once per invocation."""
    try:
        settings = Settings.from_env()
        configure_logging(settings, force=True)
        wait_for_database(
            settings.database_url,
            attempts=settings.database_wait_attempts,
            interval_seconds=settings.database_wait_interval_seconds,
        )
        run_migrations(settings.database_url)
        logger.info("database_migrations_completed")
    except Exception as exc:
        return _deployment_failure("database_migration", exc)
    return 0


def api_main() -> int:
    """Run Uvicorn from environment-validated settings with graceful signal handling."""
    try:
        settings = Settings.from_env()
        configure_logging(settings, force=True)
        if settings.auto_migrate:
            wait_for_database(
                settings.database_url,
                attempts=settings.database_wait_attempts,
                interval_seconds=settings.database_wait_interval_seconds,
            )
            run_migrations(settings.database_url)
        uvicorn.run(
            "storyforge.api.app:create_app",
            factory=True,
            host=settings.api_host,
            port=settings.api_port,
            log_level=settings.log_level.casefold(),
            access_log=False,
            log_config=None,
        )
    except Exception as exc:
        return _deployment_failure("api_startup", exc)
    return 0


def dispatcher_main() -> int:
    """Run the bounded transactional-outbox dispatcher until terminated."""
    try:
        settings = Settings.from_env()
        configure_logging(settings, force=True)
        from storyforge.application.factory import DomainServiceFactory
        from storyforge.jobs.broker import DramatiqJobBroker
        from storyforge.jobs.dispatcher import OutboxDispatcher
        from storyforge.jobs.handlers import JobHandlers
        from storyforge.jobs.worker import JobExecutor
        from storyforge.services.jobs import JobService

        engine = create_database_engine(settings.database_url)
        session_factory = create_session_factory(engine)
        broker = DramatiqJobBroker(settings.redis_url, namespace=settings.queue_prefix)
        dispatcher = OutboxDispatcher(
            session_factory,
            broker,
            settings,
            dispatcher_id=f"dispatcher-{uuid4().hex[:12]}",
        )
        job_service = JobService(session_factory, settings)
        executor = JobExecutor(
            session_factory,
            JobHandlers(
                session_factory,
                DomainServiceFactory(session_factory, settings),
                settings,
                job_service,
            ),
            settings,
            heartbeat_thread=False,
        )
        try:
            while True:
                recovered = executor.recover_expired()
                redis_recovered = dispatcher.recover_stranded()
                dispatched = dispatcher.dispatch_once()
                if dispatched == 0 and recovered == 0 and redis_recovered == 0:
                    time.sleep(settings.outbox_poll_interval)
        except KeyboardInterrupt:
            logger.info("dispatcher_stopped")
        finally:
            engine.dispose()
    except Exception as exc:
        return _deployment_failure("dispatcher", exc)
    return 0


def worker_main() -> int:
    """Run Dramatiq with one process and configured worker-thread concurrency."""
    try:
        settings = Settings.from_env()
        configure_logging(settings, force=True)
        from dramatiq.cli import main as dramatiq_main
        from dramatiq.cli import make_argument_parser

        arguments = make_argument_parser().parse_args(  # type: ignore[no-untyped-call]
            [
                "storyforge.jobs.actors:redis_broker",
                "--processes",
                "1",
                "--threads",
                str(settings.worker_concurrency),
                "--skip-logging",
            ]
        )
        dramatiq_main(arguments)  # type: ignore[no-untyped-call]
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:
        return _deployment_failure("worker", exc)
    return 0


def queue_healthcheck_main() -> int:
    """Check PostgreSQL and Redis without exposing either connection URL."""
    try:
        settings = Settings.from_env()
        probe_database(settings.database_url)
        from storyforge.jobs import DramatiqJobBroker

        if not DramatiqJobBroker(settings.redis_url, namespace=settings.queue_prefix).ping():
            raise StoryForgeError("Queue broker is unavailable")
    except Exception as exc:
        return _deployment_failure("queue_healthcheck", exc)
    return 0


def healthcheck_main() -> int:
    """Probe the configured in-container health endpoint without extra dependencies."""
    try:
        settings = Settings.from_env()
        path = os.getenv("STORYFORGE_HEALTHCHECK_PATH", "/health")
        if not path.startswith("/"):
            raise ConfigurationError("STORYFORGE_HEALTHCHECK_PATH must start with '/'")
        url = f"http://127.0.0.1:{settings.api_port}{path}"
        with urllib.request.urlopen(url, timeout=3) as response:
            if response.status != 200:
                raise StoryForgeError("Application healthcheck did not return HTTP 200")
    except Exception as exc:
        return _deployment_failure("healthcheck", exc)
    return 0


def _deployment_failure(operation: str, exc: Exception) -> int:
    """Return a non-zero code while logging only stable, credential-free metadata."""
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.ERROR)
    logger.error("%s_failed exception_type=%s", operation, type(exc).__name__)
    return 1
