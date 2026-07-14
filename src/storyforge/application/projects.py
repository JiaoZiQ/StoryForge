"""Project CRUD application service with API-safe state policies."""

from __future__ import annotations

from datetime import datetime

from storyforge.database import SessionFactory
from storyforge.enums import ProjectStatus
from storyforge.exceptions import EntityNotFoundError, InvalidStateError
from storyforge.models import Project
from storyforge.repositories import ProjectRepository
from storyforge.schemas.api import (
    DeleteResponse,
    PageResponse,
    ProjectCreateRequest,
    ProjectDetail,
    ProjectSummary,
    ProjectUpdateRequest,
)
from storyforge.schemas.domain import ProjectCreate
from storyforge.services import ProjectService

from .common import page_response


class ProjectApplicationService:
    """Expose project operations without leaking ORM entities."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def create(self, request: ProjectCreateRequest) -> ProjectDetail:
        project = ProjectService(self._session_factory).create(
            ProjectCreate(**request.model_dump(), status=ProjectStatus.CREATED)
        )
        return self.get(project.id)

    def list(
        self,
        *,
        page: int,
        page_size: int,
        status: ProjectStatus | None = None,
        genre: str | None = None,
        language: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        search: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> PageResponse[ProjectSummary]:
        with self._session_factory() as session:
            result = ProjectRepository(session).page_filtered(
                page=page,
                page_size=page_size,
                status=status.value if status is not None else None,
                genre=genre,
                language=language,
                created_from=created_from,
                created_to=created_to,
                search=search,
                sort=sort,
                order=order,
            )
            items = [_summary(item) for item in result.items]
        return page_response(result, page=page, page_size=page_size, items=items)

    def get(self, project_id: int) -> ProjectDetail:
        with self._session_factory() as session:
            repository = ProjectRepository(session)
            project = repository.get(project_id)
            if project is None:
                raise EntityNotFoundError(f"Project {project_id} was not found")
            chapters, workflows = repository.related_counts(project_id)
            return ProjectDetail(
                **_summary(project).model_dump(),
                premise=project.premise,
                tone=project.tone,
                audience=project.audience,
                additional_requirements=project.additional_requirements,
                logline=project.logline,
                themes=list(project.themes),
                world_summary=project.world_summary,
                central_conflict=project.central_conflict,
                style_guide=project.style_guide,
                chapter_count=chapters,
                workflow_count=workflows,
            )

    def update(self, project_id: int, request: ProjectUpdateRequest) -> ProjectDetail:
        changes = request.model_dump(exclude_unset=True)
        with self._session_factory.begin() as session:
            repository = ProjectRepository(session)
            project = repository.get(project_id)
            if project is None:
                raise EntityNotFoundError(f"Project {project_id} was not found")
            chapters = project.chapters
            has_plan = bool(chapters)
            has_content = any(item.content.strip() for item in chapters)
            if has_content and {"premise", "target_chapters"} & changes.keys():
                raise InvalidStateError(
                    "Premise and chapter count cannot change after content generation"
                )
            if has_plan and "premise" in changes:
                raise InvalidStateError("Premise cannot change after planning")
            repository.update(project, changes)
        return self.get(project_id)

    def delete(self, project_id: int) -> DeleteResponse:
        with self._session_factory.begin() as session:
            repository = ProjectRepository(session)
            project = repository.get(project_id)
            if project is None:
                raise EntityNotFoundError(f"Project {project_id} was not found")
            if repository.has_plan_or_content(project_id):
                raise InvalidStateError(
                    "Only projects without a plan or generated content can be deleted"
                )
            repository.delete(project)
        return DeleteResponse(deleted=True, resource_id=project_id)


def _summary(project: Project) -> ProjectSummary:
    return ProjectSummary.model_validate(project, from_attributes=True)
