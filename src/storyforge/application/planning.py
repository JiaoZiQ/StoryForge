"""Planning application service and public plan projection."""

from __future__ import annotations

from storyforge.agents import PlannerAgent
from storyforge.database import SessionFactory
from storyforge.exceptions import EntityNotFoundError, InvalidStateError
from storyforge.models import Chapter
from storyforge.prompts import build_prompt_registry
from storyforge.repositories import (
    ChapterRepository,
    CharacterRepository,
    ForeshadowingRepository,
    LocationRepository,
    ProjectRepository,
)
from storyforge.schemas.api import (
    GeneratePlanRequest,
    PlanChapter,
    PlanCharacter,
    PlanForeshadowing,
    PlanLocation,
    PlanResponse,
)
from storyforge.services import PlanningService

from .factory import DomainServiceFactory


class PlanningApplicationService:
    def __init__(self, session_factory: SessionFactory, factory: DomainServiceFactory) -> None:
        self._session_factory = session_factory
        self._factory = factory

    def generate(self, project_id: int, request: GeneratePlanRequest) -> PlanResponse:
        with self._factory.provider(
            "planning", project_id=project_id, override=request.provider
        ) as provider:
            PlanningService(
                self._session_factory, PlannerAgent(provider, build_prompt_registry())
            ).plan_project(project_id, replace_existing=request.replace_existing)
        return self.get(project_id)

    def get(self, project_id: int) -> PlanResponse:
        with self._session_factory() as session:
            project = ProjectRepository(session).get(project_id)
            if project is None:
                raise EntityNotFoundError(f"Project {project_id} was not found")
            chapters = ChapterRepository(session).list_for_project(project_id)
            if not chapters:
                raise InvalidStateError("Project has not been planned")
            characters = CharacterRepository(session).list_for_project(project_id)
            locations = LocationRepository(session).list_for_project(project_id)
            foreshadowing = ForeshadowingRepository(session).list_for_project(project_id)
            return PlanResponse(
                project_id=project.id,
                status=project.status,
                themes=list(project.themes),
                world_summary=project.world_summary or "",
                central_conflict=project.central_conflict or "",
                style_guide=project.style_guide or "",
                characters=[
                    PlanCharacter(
                        name=item.name,
                        role=item.role,
                        description=item.description,
                        goals=list(item.goals),
                        personality_traits=list(item.personality_traits),
                        speech_style=item.speech_style,
                        current_state=item.current_state,
                    )
                    for item in characters
                ],
                locations=[
                    PlanLocation(
                        name=item.name,
                        description=item.description,
                        rules=list(item.rules),
                    )
                    for item in locations
                ],
                chapter_plans=[_chapter_plan(item) for item in chapters],
                foreshadowing=[
                    PlanForeshadowing(
                        id=item.id,
                        description=item.description,
                        setup_chapter=item.setup_chapter,
                        expected_payoff_chapter=item.expected_payoff_chapter,
                        status=item.status,
                        importance=item.importance,
                    )
                    for item in foreshadowing
                ],
            )


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _chapter_plan(chapter: Chapter) -> PlanChapter:
    metadata = chapter.outline_metadata
    return PlanChapter(
        chapter_number=chapter.chapter_number,
        title=chapter.title,
        objective=chapter.objective,
        summary=chapter.outline,
        key_events=_string_list(metadata.get("key_events")),
        participating_characters=_string_list(metadata.get("participating_characters")),
        locations=_string_list(metadata.get("locations")),
        required_facts=_string_list(metadata.get("required_facts")),
        forbidden_reveals=_string_list(metadata.get("forbidden_reveals")),
    )
