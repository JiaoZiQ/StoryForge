"""End-to-end milestone-four evaluation service tests on SQLite."""

import logging

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import SQLAlchemyError

from storyforge.agents import CriticAgent, FactExtractorAgent, PlannerAgent, WriterAgent
from storyforge.consistency import ConsistencyChecker
from storyforge.consistency.rules import RULE_FUTURE_FACT
from storyforge.database import SessionFactory, create_session_factory
from storyforge.demo import (
    build_conflict_generation_provider,
    build_critic_provider,
    build_demo_provider,
)
from storyforge.enums import (
    ChapterStatus,
    ConflictSeverity,
    ConflictStatus,
    EvaluationStatus,
)
from storyforge.evaluation import EvaluationScorer, MechanicalEvaluator
from storyforge.evaluation.models import ChapterCritique, ChapterEvaluationRequest
from storyforge.exceptions import EntityNotFoundError, EvaluationError, InvalidStateError
from storyforge.llm import MockFailure, MockLLMProvider
from storyforge.models import Conflict, Evaluation, EvaluationIssue, Fact, Project
from storyforge.prompts import build_prompt_registry
from storyforge.repositories import ChapterRepository
from storyforge.schemas.domain import ProjectCreate
from storyforge.schemas.generation import ChapterGenerationRequest
from storyforge.services import (
    ChapterGenerationService,
    ContextBuilder,
    EvaluationService,
    PlanningService,
    ProjectService,
)


def _setup(engine: Engine) -> tuple[SessionFactory, Project]:
    factory = create_session_factory(engine)
    project = ProjectService(factory).create(
        ProjectCreate(
            title="M4 Test",
            genre="mystery",
            premise="A keeper investigates a moving lighthouse.",
            target_chapters=3,
            target_words_per_chapter=300,
        )
    )
    provider = build_demo_provider(3, include_canonical_attribute=True)
    registry = build_prompt_registry()
    PlanningService(factory, PlannerAgent(provider, registry)).plan_project(project.id)
    ChapterGenerationService(
        factory,
        ContextBuilder(factory),
        WriterAgent(provider, registry),
        FactExtractorAgent(provider, registry),
    ).generate(ChapterGenerationRequest(project_id=project.id, chapter_number=1))
    return factory, project


def _service(
    factory: SessionFactory,
    *,
    scenario: str = "normal",
    provider: MockLLMProvider | None = None,
    mechanical: MechanicalEvaluator | None = None,
    checker: ConsistencyChecker | None = None,
) -> EvaluationService:
    return EvaluationService(
        factory,
        mechanical or MechanicalEvaluator(),
        checker or ConsistencyChecker(),
        CriticAgent(provider or build_critic_provider(scenario), build_prompt_registry()),
        EvaluationScorer(),
    )


def _generate_conflict(factory: SessionFactory, project_id: int) -> None:
    provider = build_conflict_generation_provider(2)
    registry = build_prompt_registry()
    ChapterGenerationService(
        factory,
        ContextBuilder(factory),
        WriterAgent(provider, registry),
        FactExtractorAgent(provider, registry),
    ).generate(ChapterGenerationRequest(project_id=project_id, chapter_number=2))


def test_normal_evaluation_persists_details_status_and_versions(db_engine: Engine) -> None:
    factory, project = _setup(db_engine)
    service = _service(factory)

    first = service.evaluate(ChapterEvaluationRequest(project_id=project.id, chapter_number=1))
    second = service.evaluate(ChapterEvaluationRequest(project_id=project.id, chapter_number=1))

    assert first.passed is True
    assert first.recommended_action == "accept"
    assert (first.evaluation_version, second.evaluation_version) == (1, 2)
    history = service.list_evaluations(project.id, 1)
    assert [item.evaluation_id for item in history] == [
        first.evaluation_id,
        second.evaluation_id,
    ]
    with factory() as session:
        chapter = ChapterRepository(session).get_by_number(project.id, 1)
        assert chapter is not None
        assert chapter.status is ChapterStatus.EVALUATED_PASSED
        evaluations = list(
            session.scalars(
                select(Evaluation)
                .where(Evaluation.chapter_id == chapter.id)
                .order_by(Evaluation.evaluation_version)
            )
        )
        assert len(evaluations) == 2
        assert all(item.raw_scores and item.weighted_scores for item in evaluations)
        assert all(item.evaluator_versions and item.prompt_versions for item in evaluations)
        assert session.scalar(select(func.count(EvaluationIssue.id))) >= 2


def test_conflict_evaluation_persists_filterable_conflict_and_status(db_engine: Engine) -> None:
    factory, project = _setup(db_engine)
    _service(factory).evaluate(ChapterEvaluationRequest(project_id=project.id, chapter_number=1))
    _generate_conflict(factory, project.id)

    result = _service(factory, scenario="conflict").evaluate(
        ChapterEvaluationRequest(project_id=project.id, chapter_number=2)
    )
    assert result.passed is False
    assert result.conflict_count == 1
    assert result.recommended_action == "human_review"

    service = _service(factory)
    conflicts = service.list_conflicts(
        project.id,
        chapter_number=2,
        severity=ConflictSeverity.HIGH,
        status=ConflictStatus.OPEN,
    )
    assert len(conflicts) == 1
    assert conflicts[0].existing_fact_id is not None
    updated = service.update_conflict_status(project.id, conflicts[0].id, ConflictStatus.RESOLVED)
    assert updated.status is ConflictStatus.RESOLVED
    assert updated.resolved_at is not None
    reopened = service.update_conflict_status(project.id, conflicts[0].id, ConflictStatus.OPEN)
    assert reopened.resolved_at is None


def test_missing_content_fact_extraction_and_illegal_status_are_rejected(
    db_engine: Engine,
) -> None:
    factory, project = _setup(db_engine)
    with factory.begin() as session:
        chapter2 = ChapterRepository(session).get_by_number(project.id, 2)
        chapter3 = ChapterRepository(session).get_by_number(project.id, 3)
        assert chapter2 is not None and chapter3 is not None
        chapter2.content = "Draft preserved after extraction error."
        chapter2.status = ChapterStatus.FACT_EXTRACTION_FAILED
        chapter3.content = "Evaluation is already running."
        chapter3.status = ChapterStatus.EVALUATING

    service = _service(factory)
    with pytest.raises(InvalidStateError, match="Fact extraction"):
        service.evaluate(ChapterEvaluationRequest(project_id=project.id, chapter_number=2))
    with pytest.raises(InvalidStateError, match="status"):
        service.evaluate(ChapterEvaluationRequest(project_id=project.id, chapter_number=3))

    with factory.begin() as session:
        chapter1 = ChapterRepository(session).get_by_number(project.id, 1)
        assert chapter1 is not None
        chapter1.content = ""
    with pytest.raises(InvalidStateError, match="generated content"):
        service.evaluate(ChapterEvaluationRequest(project_id=project.id, chapter_number=1))


def test_critic_failure_preserves_partial_local_result_and_allows_retry(
    db_engine: Engine,
) -> None:
    factory, project = _setup(db_engine)
    configured = build_critic_provider()
    request = configured.requests
    assert request == []
    valid = (
        CriticAgent(configured, build_prompt_registry())
        .critique(_service_context(project.id))
        .output
    )
    failing = MockLLMProvider({ChapterCritique: valid}, failures=[MockFailure.CALL_FAILURE])

    with pytest.raises(EvaluationError, match="local evaluation results were preserved"):
        _service(factory, provider=failing).evaluate(
            ChapterEvaluationRequest(project_id=project.id, chapter_number=1)
        )
    with factory() as session:
        partial = session.scalar(select(Evaluation))
        assert partial is not None
        assert partial.status is EvaluationStatus.PARTIAL_FAILED
        assert partial.mechanical_score > 0
        assert partial.consistency_score > 0
        assert partial.weighted_scores == {}
        chapter = ChapterRepository(session).get_by_number(project.id, 1)
        assert chapter is not None
        assert chapter.status is ChapterStatus.EVALUATION_FAILED

    retry = _service(factory).evaluate(
        ChapterEvaluationRequest(project_id=project.id, chapter_number=1)
    )
    assert retry.evaluation_version == 2
    assert retry.status is EvaluationStatus.COMPLETED


def _service_context(project_id: int):
    from storyforge.evaluation.models import CriticContext

    return CriticContext(
        project_id=project_id,
        chapter_id=1,
        chapter_number=1,
        genre="mystery",
        premise="test",
        outline={},
        content="test content",
        summary="test",
        mechanical_summary={},
        consistency_summary={},
    )


class _BrokenMechanical(MechanicalEvaluator):
    def evaluate(self, request):
        raise RuntimeError("mechanical failed")


class _BrokenConsistency(ConsistencyChecker):
    def check(self, request):
        raise RuntimeError("consistency failed")


@pytest.mark.parametrize("component", ("mechanical", "consistency"))
def test_local_component_failures_create_no_evaluation_and_restore_failure_state(
    db_engine: Engine, component: str
) -> None:
    factory, project = _setup(db_engine)
    service = _service(
        factory,
        mechanical=_BrokenMechanical() if component == "mechanical" else None,
        checker=_BrokenConsistency() if component == "consistency" else None,
    )
    with pytest.raises(EvaluationError, match="Local chapter evaluation failed"):
        service.evaluate(ChapterEvaluationRequest(project_id=project.id, chapter_number=1))

    with factory() as session:
        assert session.scalar(select(func.count(Evaluation.id))) == 0
        chapter = ChapterRepository(session).get_by_number(project.id, 1)
        assert chapter is not None
        assert chapter.status is ChapterStatus.EVALUATION_FAILED


def test_database_failure_rolls_back_new_attempt_and_preserves_old_evaluation(
    db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory, project = _setup(db_engine)
    service = _service(factory)
    first = service.evaluate(ChapterEvaluationRequest(project_id=project.id, chapter_number=1))

    def fail_persistence(*args: object, **kwargs: object) -> None:
        raise SQLAlchemyError("database failed")

    monkeypatch.setattr(service, "_add_issues", fail_persistence)
    with pytest.raises(EvaluationError, match="persistence failed"):
        service.evaluate(ChapterEvaluationRequest(project_id=project.id, chapter_number=1))

    with factory() as session:
        evaluations = list(session.scalars(select(Evaluation)))
        assert [item.id for item in evaluations] == [first.evaluation_id]
        chapter = ChapterRepository(session).get_by_number(project.id, 1)
        assert chapter is not None
        assert chapter.status is ChapterStatus.EVALUATION_FAILED


def test_future_facts_secrets_and_content_are_not_logged_or_sent(
    db_engine: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    factory, project = _setup(db_engine)
    _generate_conflict(factory, project.id)
    with factory.begin() as session:
        chapter3 = ChapterRepository(session).get_by_number(project.id, 3)
        assert chapter3 is not None
        session.add(
            Fact(
                project_id=project.id,
                chapter_id=chapter3.id,
                subject="future",
                predicate="knows",
                object="FUTURE_ONLY_SECRET",
                fact_type="knowledge",
                valid_from_chapter=3,
                confidence=1,
                source_quote="FUTURE_ONLY_SECRET",
            )
        )
        project_row = session.get(Project, project.id)
        assert project_row is not None
        project_row.characters[0].secrets = ["AUTHOR_ONLY_SECRET"]
        chapter2 = ChapterRepository(session).get_by_number(project.id, 2)
        assert chapter2 is not None
        full_content = chapter2.content

    provider = build_critic_provider("conflict")
    caplog.set_level(logging.INFO)
    _service(factory, provider=provider).evaluate(
        ChapterEvaluationRequest(project_id=project.id, chapter_number=2)
    )
    prompt_text = "\n".join(
        message.content for request in provider.requests for message in request.messages
    )
    assert "FUTURE_ONLY_SECRET" not in prompt_text
    assert "AUTHOR_ONLY_SECRET" not in prompt_text
    assert all(conflict.rule_code != RULE_FUTURE_FACT for conflict in result_to_conflicts(factory))
    assert full_content not in caplog.text
    assert "AUTHOR_ONLY_SECRET" not in caplog.text


def result_to_conflicts(factory: SessionFactory) -> list[Conflict]:
    with factory() as session:
        return list(session.scalars(select(Conflict)))


def test_conflict_lookup_enforces_project_ownership(db_engine: Engine) -> None:
    factory, project = _setup(db_engine)
    _generate_conflict(factory, project.id)
    _service(factory, scenario="conflict").evaluate(
        ChapterEvaluationRequest(project_id=project.id, chapter_number=2)
    )
    conflict = _service(factory).list_conflicts(project.id)[0]
    with pytest.raises(EntityNotFoundError, match="not found"):
        _service(factory).update_conflict_status(
            project.id + 100, conflict.id, ConflictStatus.IGNORED
        )
