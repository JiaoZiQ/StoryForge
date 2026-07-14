"""Transactional project planning orchestration."""

from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError

from storyforge.agents import PlannerAgent
from storyforge.database import SessionFactory
from storyforge.enums import ProjectStatus
from storyforge.exceptions import (
    AgentExecutionError,
    EntityNotFoundError,
    InvalidStateError,
    PlanningValidationError,
)
from storyforge.models import Chapter, Character, Foreshadowing, Location, StoryRule
from storyforge.repositories import (
    ChapterRepository,
    ProjectRepository,
    WorkflowRunRepository,
)
from storyforge.schemas.planning import NovelPlan, PlanningRequest


class PlanningService:
    """Plan a project, validate it, and persist the aggregate atomically."""

    def __init__(self, session_factory: SessionFactory, planner: PlannerAgent) -> None:
        self._session_factory = session_factory
        self._planner = planner

    def plan_project(self, project_id: int, *, replace_existing: bool = False) -> NovelPlan:
        """Generate and atomically persist a complete project plan."""
        request = self._prepare_request(project_id, replace_existing=replace_existing)
        try:
            agent_result = self._planner.plan(request)
            self._persist_plan(
                project_id,
                agent_result.output,
                source_versions=agent_result.prompt_versions,
                replace_existing=replace_existing,
            )
        except (AgentExecutionError, PlanningValidationError, SQLAlchemyError):
            self._mark_failed(project_id)
            raise
        return agent_result.output

    def _prepare_request(self, project_id: int, *, replace_existing: bool) -> PlanningRequest:
        with self._session_factory.begin() as session:
            project = ProjectRepository(session).get(project_id)
            if project is None:
                raise EntityNotFoundError(f"Project {project_id} was not found")
            if WorkflowRunRepository(session).active_for_project(project_id) is not None:
                raise InvalidStateError("A project with an active workflow cannot be replanned")
            chapters = ChapterRepository(session).list_for_project(project_id)
            has_plan = bool(chapters or project.characters or project.locations)
            has_content = any(chapter.content.strip() for chapter in chapters)
            if has_content:
                raise InvalidStateError("A project with generated content cannot be replanned")
            if has_plan and not replace_existing:
                raise InvalidStateError("Project already has a plan; pass replace_existing=True")
            if project.status in {ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED}:
                raise InvalidStateError(f"Project cannot be planned from status {project.status}")
            request = PlanningRequest(
                project_id=project.id,
                title=project.title,
                genre=project.genre,
                premise=project.premise,
                target_chapters=project.target_chapters,
                target_words_per_chapter=project.target_words_per_chapter,
                language=project.language,
                tone=project.tone,
                audience=project.audience,
            )
            project.status = ProjectStatus.PLANNING
        return request

    def _persist_plan(
        self,
        project_id: int,
        plan: NovelPlan,
        *,
        source_versions: dict[str, str],
        replace_existing: bool,
    ) -> None:
        with self._session_factory.begin() as session:
            project = ProjectRepository(session).get(project_id)
            if project is None:
                raise EntityNotFoundError(f"Project {project_id} disappeared during planning")
            if replace_existing:
                for model in (Chapter, Character, Location, StoryRule, Foreshadowing):
                    session.execute(delete(model).where(model.project_id == project_id))

            project.logline = plan.logline
            project.themes = list(plan.themes)
            project.world_summary = plan.world_summary
            project.central_conflict = plan.central_conflict
            project.ending_direction = plan.ending_direction
            project.style_guide = plan.style_guide
            project.status = ProjectStatus.PLANNED
            session.add_all(
                Character(
                    project_id=project_id,
                    name=item.name,
                    role=item.role,
                    description=item.description,
                    goals=list(item.goals),
                    personality="、".join(item.personality),
                    personality_traits=list(item.personality),
                    speech_style=item.speech_style,
                    current_state=item.initial_state,
                    secrets=list(item.secrets),
                )
                for item in plan.characters
            )
            session.add_all(
                Location(
                    project_id=project_id,
                    name=item.name,
                    description=item.description,
                    rules=list(item.rules),
                )
                for item in plan.locations
            )
            source = ",".join(f"{key}@{value}" for key, value in source_versions.items())
            session.add_all(
                StoryRule(
                    project_id=project_id,
                    category=item.category,
                    statement=item.statement,
                    source=source,
                    active=True,
                )
                for item in plan.story_rules
            )
            session.add_all(
                Chapter(
                    project_id=project_id,
                    chapter_number=item.chapter_number,
                    title=item.title,
                    outline=item.summary,
                    objective=item.objective,
                    outline_metadata={
                        "summary": item.summary,
                        "key_events": item.key_events,
                        "participating_characters": item.participating_characters,
                        "locations": item.locations,
                        "required_facts": item.required_facts,
                        "forbidden_reveals": item.forbidden_reveals,
                        "setup_foreshadowing": item.setup_foreshadowing,
                        "payoff_foreshadowing": item.payoff_foreshadowing,
                        "ending_hook": item.ending_hook,
                    },
                )
                for item in plan.chapter_plans
            )
            session.add_all(
                Foreshadowing(
                    project_id=project_id,
                    setup_chapter=item.setup_chapter,
                    expected_payoff_chapter=item.expected_payoff_chapter,
                    description=item.description,
                    importance=item.importance,
                )
                for item in plan.foreshadowing
            )

    def _mark_failed(self, project_id: int) -> None:
        with self._session_factory.begin() as session:
            project = ProjectRepository(session).get(project_id)
            if project is not None:
                project.status = ProjectStatus.FAILED
