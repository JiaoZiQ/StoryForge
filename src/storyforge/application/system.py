"""Liveness and database-backed readiness projections."""

from typing import Literal

from storyforge import __version__
from storyforge.database import SessionFactory
from storyforge.exceptions import DatabaseNotReadyError, QueueUnavailableError
from storyforge.jobs.broker import DramatiqJobBroker
from storyforge.migrations import MIGRATION_HEAD
from storyforge.repositories import SystemRepository
from storyforge.schemas.api import HealthResponse, ReadinessResponse
from storyforge.settings import Settings


class SystemApplicationService:
    def __init__(self, session_factory: SessionFactory, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings

    def health(self) -> HealthResponse:
        return HealthResponse(
            status="ok", version=__version__, environment=self._settings.environment
        )

    def readiness(self) -> ReadinessResponse:
        with self._session_factory() as session:
            repository = SystemRepository(session)
            repository.ping()
            revision = repository.migration_revision()
        if revision != MIGRATION_HEAD:
            raise DatabaseNotReadyError("Database migrations are incomplete")
        queue: Literal["ok", "inline"] = "inline"
        if self._settings.job_execution_mode == "queue":
            if not DramatiqJobBroker(
                self._settings.redis_url, namespace=self._settings.queue_prefix
            ).ping():
                raise QueueUnavailableError("Queue broker is unavailable")
            queue = "ok"
        return ReadinessResponse(
            status="ready",
            database="ok",
            migration_revision=revision,
            provider=self._settings.llm_provider,
            queue=queue,
        )
