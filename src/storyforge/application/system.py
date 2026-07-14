"""Liveness and database-backed readiness projections."""

from storyforge import __version__
from storyforge.database import SessionFactory
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
        return ReadinessResponse(
            status="ready",
            database="ok",
            migration_revision=revision,
            provider=self._settings.llm_provider,
        )
