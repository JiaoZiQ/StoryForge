"""Project creation application service."""

from storyforge.database import SessionFactory
from storyforge.models import Project
from storyforge.repositories import ProjectRepository
from storyforge.schemas.domain import ProjectCreate


class ProjectService:
    """Create project aggregate roots without exposing repository transactions."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def create(self, request: ProjectCreate) -> Project:
        """Persist one new project atomically."""
        with self._session_factory.begin() as session:
            project = Project(**request.model_dump())
            ProjectRepository(session).add(project)
        return project
