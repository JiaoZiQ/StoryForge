"""Leak-free, budget-aware writer context assembly."""

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ValidationError

from storyforge.database import SessionFactory
from storyforge.exceptions import ContextBuildError, EntityNotFoundError, InvalidStateError
from storyforge.repositories import (
    ChapterRepository,
    CharacterRepository,
    FactRepository,
    ForeshadowingRepository,
    LocationRepository,
    ProjectRepository,
    StoryRuleRepository,
)
from storyforge.schemas.context import (
    ChapterContext,
    ChapterOutlineContext,
    CharacterContext,
    ContextBudgetMetadata,
    ContextBuildRequest,
    FactContext,
    ForeshadowingContext,
    LocationContext,
    ProjectContext,
    RecentChapterContext,
    RuleContext,
)


def _size(value: BaseModel) -> int:
    return len(value.model_dump_json())


class ContextBuilder:
    """Build a typed context from persisted data without exposing future knowledge."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def build(self, request: ContextBuildRequest) -> ChapterContext:
        """Assemble and budget a writer context; the current outline is mandatory."""
        with self._session_factory() as session:
            project = ProjectRepository(session).get(request.project_id)
            if project is None:
                raise EntityNotFoundError(f"Project {request.project_id} was not found")
            chapter = ChapterRepository(session).get_by_number(
                request.project_id, request.chapter_number
            )
            if chapter is None:
                raise EntityNotFoundError(
                    f"Chapter {request.chapter_number} was not found for project {request.project_id}"
                )
            if not all(
                (
                    project.world_summary,
                    project.central_conflict,
                    project.ending_direction,
                    project.style_guide,
                )
            ):
                raise InvalidStateError("Project must be planned before context can be built")
            try:
                project_context = ProjectContext(
                    title=project.title,
                    genre=project.genre,
                    premise=project.premise,
                    themes=project.themes,
                    world_summary=project.world_summary or "",
                    central_conflict=project.central_conflict or "",
                    style_guide=project.style_guide or "",
                    language=project.language,
                    tone=project.tone,
                    audience=project.audience,
                )
                outline = ChapterOutlineContext.model_validate(
                    {
                        "chapter_number": chapter.chapter_number,
                        "title": chapter.title,
                        "objective": chapter.objective,
                        **chapter.outline_metadata,
                    }
                )
            except ValidationError as exc:
                raise ContextBuildError("Persisted planning data is structurally invalid") from exc

            character_names = set(outline.participating_characters)
            characters = [
                CharacterContext(
                    name=item.name,
                    role=item.role,
                    description=item.description,
                    goals=item.goals,
                    personality=item.personality_traits,
                    speech_style=item.speech_style,
                    current_state=item.current_state,
                )
                for item in CharacterRepository(session).list_for_project(request.project_id)
                if item.name in character_names
            ][: request.max_characters]
            location_names = set(outline.locations)
            locations = [
                LocationContext(name=item.name, description=item.description, rules=item.rules)
                for item in LocationRepository(session).list_for_project(request.project_id)
                if item.name in location_names
            ]
            rules = [
                RuleContext(category=item.category, statement=item.statement)
                for item in StoryRuleRepository(session).list_active_for_project(request.project_id)
            ]
            facts = [
                FactContext(
                    subject=item.subject,
                    predicate=item.predicate,
                    object=item.object,
                    fact_type=item.fact_type,
                    confidence=item.confidence,
                    source_chapter=item.chapter.chapter_number,
                )
                for item in self._relevant_facts(
                    FactRepository(session).list_known_before(
                        request.project_id, request.chapter_number
                    ),
                    outline,
                )
            ]
            foreshadowing = [
                ForeshadowingContext(
                    foreshadowing_id=item.id,
                    description=item.description,
                    setup_chapter=item.setup_chapter,
                    expected_payoff_chapter=item.expected_payoff_chapter,
                    importance=item.importance,
                )
                for item in ForeshadowingRepository(session).list_active_before(
                    request.project_id, request.chapter_number
                )
            ]
            recent = [
                RecentChapterContext(
                    chapter_number=item.chapter_number,
                    title=item.title,
                    summary=item.summary or "",
                )
                for item in reversed(
                    ChapterRepository(session).list_for_project(request.project_id)
                )
                if item.chapter_number < request.chapter_number and item.summary
            ][: request.recent_chapter_limit]

        return self._apply_budget(
            request,
            project_context,
            outline,
            rules=rules,
            characters=characters,
            facts=facts,
            foreshadowing=foreshadowing,
            recent=recent,
            locations=locations,
        )

    @staticmethod
    def _relevant_facts(facts: Iterable[Any], outline: ChapterOutlineContext) -> list[Any]:
        terms = {
            "".join(term.casefold().split())
            for term in (
                *outline.participating_characters,
                *outline.locations,
                *outline.required_facts,
            )
            if term.strip()
        }
        relevant = []
        for fact in facts:
            searchable = "".join(
                f"{fact.subject} {fact.predicate} {fact.object}".casefold().split()
            )
            if not terms or any(term in searchable or searchable in term for term in terms):
                relevant.append(fact)
        return relevant

    @staticmethod
    def _apply_budget(
        request: ContextBuildRequest,
        project: ProjectContext,
        outline: ChapterOutlineContext,
        **categories: list[Any],
    ) -> ChapterContext:
        mandatory_size = _size(project) + _size(outline)
        used = mandatory_size
        candidate_items = sum(len(items) for items in categories.values())
        included: dict[str, list[Any]] = {name: [] for name in categories}
        omitted_categories: list[str] = []
        for category, items in categories.items():
            for item in items:
                item_size = _size(item)
                if used + item_size <= request.max_context_chars:
                    included[category].append(item)
                    used += item_size
                elif category not in omitted_categories:
                    omitted_categories.append(category)
        included_items = sum(len(items) for items in included.values())
        return ChapterContext(
            project_id=request.project_id,
            project=project,
            current_outline=outline,
            rules=included["rules"],
            characters=included["characters"],
            known_facts=included["facts"],
            active_foreshadowing=included["foreshadowing"],
            recent_chapters=included["recent"],
            locations=included["locations"],
            budget=ContextBudgetMetadata(
                max_chars=request.max_context_chars,
                estimated_chars=used,
                candidate_items=candidate_items,
                included_items=included_items,
                omitted_items=candidate_items - included_items,
                omitted_categories=omitted_categories,
                mandatory_outline_exceeded_budget=mandatory_size > request.max_context_chars,
            ),
        )
