"""End-to-end milestone-three service tests on isolated SQLite."""

import pytest
from sqlalchemy import Engine, select

from storyforge.agents import FactExtractorAgent, PlannerAgent, WriterAgent
from storyforge.consistency.normalizer import FactNormalizer
from storyforge.database import create_session_factory
from storyforge.demo import build_demo_provider
from storyforge.enums import ChapterStatus, ChapterVersionStatus, ProjectStatus
from storyforge.exceptions import (
    ChapterGenerationError,
    InvalidStateError,
    PlanningValidationError,
)
from storyforge.llm import MockFailure, MockLLMProvider
from storyforge.models import ChapterVersion, Fact, Project
from storyforge.prompts import build_prompt_registry
from storyforge.repositories import ChapterRepository, ProjectRepository
from storyforge.schemas.context import ContextBuildRequest
from storyforge.schemas.domain import ProjectCreate
from storyforge.schemas.generation import (
    ChapterGenerationRequest,
    FactExtractionResult,
)
from storyforge.services import (
    ChapterGenerationService,
    ContextBuilder,
    PlanningService,
    ProjectService,
)


def _create_project(engine: Engine, *, chapters: int = 3) -> tuple[object, Project]:
    factory = create_session_factory(engine)
    project = ProjectService(factory).create(
        ProjectCreate(
            title="雾岬潮汐",
            genre="悬疑奇幻",
            premise="档案修复师追查随潮汐消失的灯塔。",
            target_chapters=chapters,
            target_words_per_chapter=1800,
        )
    )
    return factory, project


def _plan(factory: object, project: Project) -> None:
    provider = build_demo_provider(project.target_chapters)
    PlanningService(
        factory,  # type: ignore[arg-type]
        PlannerAgent(provider, build_prompt_registry()),
    ).plan_project(project.id)


def _generator(factory: object, chapter_number: int = 1) -> ChapterGenerationService:
    provider = build_demo_provider(3, chapter_number)
    registry = build_prompt_registry()
    return ChapterGenerationService(
        factory,  # type: ignore[arg-type]
        ContextBuilder(factory),  # type: ignore[arg-type]
        WriterAgent(provider, registry),
        FactExtractorAgent(provider, registry),
    )


def test_complete_offline_path_persists_plan_context_draft_facts_and_version(
    db_engine: Engine,
) -> None:
    factory, project = _create_project(db_engine)
    _plan(factory, project)

    before = ContextBuilder(factory).build(  # type: ignore[arg-type]
        ContextBuildRequest(project_id=project.id, chapter_number=1)
    )
    result = _generator(factory).generate(
        ChapterGenerationRequest(project_id=project.id, chapter_number=1)
    )

    assert before.author_secrets == []
    assert before.current_outline.chapter_number == 1
    assert result.status == ChapterStatus.GENERATED
    assert result.fact_count == 1
    assert result.character_update_count == 1
    with factory() as session:  # type: ignore[operator]
        persisted = ChapterRepository(session).get_by_number(project.id, 1)
        assert persisted is not None
        assert len(persisted.facts) == 1
        assert len(persisted.versions) == 1
        assert persisted.versions[0].content == persisted.content
        assert persisted.project.status == ProjectStatus.GENERATING
        assert persisted.project.characters[0].current_state.startswith("已进入")
        assert len(persisted.project.foreshadowings) == 1


def test_context_excludes_future_sources_and_applies_budget(db_engine: Engine) -> None:
    factory, project = _create_project(db_engine)
    _plan(factory, project)
    _generator(factory).generate(ChapterGenerationRequest(project_id=project.id, chapter_number=1))
    with factory.begin() as session:  # type: ignore[attr-defined]
        future = ChapterRepository(session).get_by_number(project.id, 3)
        assert future is not None
        future_version = ChapterVersion(
            chapter_id=future.id,
            version=1,
            title=future.title,
            content="未来章节才会出现的句子。",
            summary="未来摘要",
            status=ChapterVersionStatus.ACCEPTED,
            source="test",
        )
        session.add(future_version)
        session.flush()
        future.current_version_id = future_version.id
        future.accepted_version_id = future_version.id
        session.add(
            Fact(
                project_id=project.id,
                chapter_id=future.id,
                chapter_version_id=future_version.id,
                normalized_hash=FactNormalizer().identity_hash("林舟", "得知", "最终真相"),
                subject="林舟",
                predicate="得知",
                object="最终真相",
                fact_type="knowledge",
                valid_from_chapter=1,
                confidence=1,
                source_quote="未来章节才会出现的句子。",
            )
        )

    context = ContextBuilder(factory).build(  # type: ignore[arg-type]
        ContextBuildRequest(project_id=project.id, chapter_number=2)
    )
    assert [item.object for item in context.known_facts] == ["潮汐纹铜钥匙"]
    assert [item.chapter_number for item in context.recent_chapters] == [1]
    assert "ending_direction" not in context.project.model_dump()
    assert context.author_secrets == []

    tiny = ContextBuilder(factory).build(  # type: ignore[arg-type]
        ContextBuildRequest(project_id=project.id, chapter_number=2, max_context_chars=50)
    )
    assert tiny.current_outline.chapter_number == 2
    assert tiny.budget.mandatory_outline_exceeded_budget is True
    assert tiny.budget.omitted_items == tiny.budget.candidate_items


def test_replan_and_regeneration_require_explicit_overwrite_and_preserve_snapshots(
    db_engine: Engine,
) -> None:
    factory, project = _create_project(db_engine)
    _plan(factory, project)
    planner = PlanningService(
        factory,  # type: ignore[arg-type]
        PlannerAgent(build_demo_provider(3), build_prompt_registry()),
    )
    with pytest.raises(InvalidStateError, match="already has a plan"):
        planner.plan_project(project.id)
    planner.plan_project(project.id, replace_existing=True)

    generator = _generator(factory)
    generator.generate(ChapterGenerationRequest(project_id=project.id, chapter_number=1))
    with pytest.raises(InvalidStateError, match="already has content"):
        generator.generate(ChapterGenerationRequest(project_id=project.id, chapter_number=1))
    generator.generate(
        ChapterGenerationRequest(project_id=project.id, chapter_number=1, regenerate=True)
    )

    with factory() as session:  # type: ignore[operator]
        chapter = ChapterRepository(session).get_by_number(project.id, 1)
        assert chapter is not None
        assert chapter.version == 2
        assert [item.version for item in chapter.versions] == [1, 2]
        assert session.scalar(
            select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id).limit(1)
        )


def test_planner_validation_and_fact_extraction_failures_set_recoverable_states(
    db_engine: Engine,
) -> None:
    factory, project = _create_project(db_engine)
    invalid_planner = PlanningService(
        factory,  # type: ignore[arg-type]
        PlannerAgent(build_demo_provider(2), build_prompt_registry()),
    )
    with pytest.raises(PlanningValidationError, match="chapter count"):
        invalid_planner.plan_project(project.id)
    with factory() as session:  # type: ignore[operator]
        assert ProjectRepository(session).get(project.id).status == ProjectStatus.FAILED  # type: ignore[union-attr]

    _plan(factory, project)
    writer_provider = build_demo_provider(3)
    failing_extractor = MockLLMProvider(
        {FactExtractionResult: FactExtractionResult()},
        failures=[MockFailure.CALL_FAILURE],
    )
    registry = build_prompt_registry()
    service = ChapterGenerationService(
        factory,  # type: ignore[arg-type]
        ContextBuilder(factory),  # type: ignore[arg-type]
        WriterAgent(writer_provider, registry),
        FactExtractorAgent(failing_extractor, registry),
    )
    with pytest.raises(ChapterGenerationError, match="draft was preserved"):
        service.generate(ChapterGenerationRequest(project_id=project.id, chapter_number=1))

    with factory() as session:  # type: ignore[operator]
        chapter = ChapterRepository(session).get_by_number(project.id, 1)
        assert chapter is not None
        assert chapter.content
        assert chapter.status == ChapterStatus.FACT_EXTRACTION_FAILED
        assert chapter.project.status == ProjectStatus.FAILED
        assert chapter.facts == []


def test_explicit_regeneration_is_allowed_after_a_single_chapter_project_completes(
    db_engine: Engine,
) -> None:
    factory, project = _create_project(db_engine, chapters=1)
    _plan(factory, project)
    provider = build_demo_provider(1)
    registry = build_prompt_registry()
    service = ChapterGenerationService(
        factory,  # type: ignore[arg-type]
        ContextBuilder(factory),  # type: ignore[arg-type]
        WriterAgent(provider, registry),
        FactExtractorAgent(provider, registry),
    )

    service.generate(ChapterGenerationRequest(project_id=project.id, chapter_number=1))
    second = service.generate(
        ChapterGenerationRequest(
            project_id=project.id,
            chapter_number=1,
            regenerate=True,
        )
    )

    assert second.version == 2
    with factory() as session:  # type: ignore[operator]
        persisted = ChapterRepository(session).get_by_number(project.id, 1)
        assert persisted is not None
        assert persisted.project.status == ProjectStatus.COMPLETED
        assert len(persisted.versions) == 2
