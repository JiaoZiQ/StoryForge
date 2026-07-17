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
from storyforge.retrieval import (
    HybridRetrievalRequest,
    HybridRetrievalResult,
    HybridRetriever,
    RetrievalError,
    RetrievalQueryBuilder,
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
    MemoryContext,
    ProjectContext,
    RecentChapterContext,
    RuleContext,
)


def _size(value: BaseModel) -> int:
    return len(value.model_dump_json())


class ContextBuilder:
    """Build a typed context from persisted data without exposing future knowledge."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        hybrid_retriever: HybridRetriever | None = None,
        retrieval_top_k: int = 20,
        retrieval_max_context_chars: int = 16_000,
    ) -> None:
        self._session_factory = session_factory
        self._hybrid_retriever = hybrid_retriever
        self._retrieval_top_k = retrieval_top_k
        self._retrieval_max_context_chars = retrieval_max_context_chars

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

        retrieval = self._retrieve_memory(
            request,
            outline,
            recent,
            foreshadowing,
        )
        fact_keys = {
            self._canonical_text(f"{item.subject} {item.predicate} {item.object}") for item in facts
        }
        memory = [
            MemoryContext(
                hit_id=item.id,
                source_type=item.source_type,
                content=item.content,
                score=item.score,
                source_routes=[source.value for source in item.matched_sources],
                source_chapter=item.chapter_number,
                explanation=item.explanation,
            )
            for item in retrieval.hits
            if not (item.source_type == "fact" and self._canonical_text(item.content) in fact_keys)
        ]

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
            memory=memory,
            retrieval=retrieval,
        )

    def _retrieve_memory(
        self,
        request: ContextBuildRequest,
        outline: ChapterOutlineContext,
        recent: list[RecentChapterContext],
        foreshadowing: list[ForeshadowingContext],
    ) -> HybridRetrievalResult:
        if self._hybrid_retriever is None:
            return HybridRetrievalResult(
                query=outline.objective,
                hits=[],
                total_candidates=0,
                keyword_candidates=0,
                vector_candidates=0,
                fact_candidates=0,
                graph_candidates=0,
                deduplicated_count=0,
                omitted_count=0,
                estimated_chars=0,
                retrieval_version="disabled",
                filters_applied=[],
            )
        plan = RetrievalQueryBuilder().build(
            outline,
            previous_summary=recent[0].summary if recent else "",
            active_foreshadowing=[item.description for item in foreshadowing],
        )
        try:
            return self._hybrid_retriever.retrieve(
                HybridRetrievalRequest(
                    project_id=request.project_id,
                    query=plan.semantic_query,
                    current_chapter=request.chapter_number,
                    character_names=plan.character_names,
                    location_names=plan.location_names,
                    source_types=plan.source_types,
                    top_k=self._retrieval_top_k,
                    max_context_chars=max(
                        100,
                        min(
                            request.max_context_chars,
                            self._retrieval_max_context_chars,
                        ),
                    ),
                )
            )
        except RetrievalError:
            return HybridRetrievalResult(
                query=plan.semantic_query,
                hits=[],
                total_candidates=0,
                keyword_candidates=0,
                vector_candidates=0,
                fact_candidates=0,
                graph_candidates=0,
                deduplicated_count=0,
                omitted_count=0,
                estimated_chars=0,
                retrieval_version="unavailable",
                filters_applied=["project_id", "accepted_status", "chapter_cutoff"],
                degraded=True,
                degraded_reasons=["all_routes_unavailable"],
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
    def _canonical_text(value: str) -> str:
        return "".join(character for character in value.casefold() if character.isalnum())

    @staticmethod
    def _apply_budget(
        request: ContextBuildRequest,
        project: ProjectContext,
        outline: ChapterOutlineContext,
        retrieval: HybridRetrievalResult,
        **categories: list[Any],
    ) -> ChapterContext:
        mandatory_rules = categories.pop("rules", [])
        mandatory_size = (
            _size(project) + _size(outline) + sum(_size(rule) for rule in mandatory_rules)
        )
        used = mandatory_size
        candidate_items = len(mandatory_rules) + sum(len(items) for items in categories.values())
        included: dict[str, list[Any]] = {
            "rules": list(mandatory_rules),
            **{name: [] for name in categories},
        }
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
        memory_items = included["memory"]
        source_composition: dict[str, int] = {}
        for item in memory_items:
            for source in item.source_routes:
                source_composition[source] = source_composition.get(source, 0) + 1
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
            memory_hits=included["memory"],
            budget=ContextBudgetMetadata(
                max_chars=request.max_context_chars,
                estimated_chars=used,
                candidate_items=candidate_items,
                included_items=included_items,
                omitted_items=candidate_items - included_items,
                omitted_categories=omitted_categories,
                mandatory_outline_exceeded_budget=mandatory_size > request.max_context_chars,
                retrieval_version=retrieval.retrieval_version,
                retrieval_query=retrieval.query,
                retrieval_hit_ids=[item.hit_id for item in memory_items],
                retrieval_source_composition=source_composition,
                retrieval_degraded=retrieval.degraded,
                retrieval_degraded_reasons=retrieval.degraded_reasons,
            ),
        )
