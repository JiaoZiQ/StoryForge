"""Durable Milestone 5 graph, version history, facts, and recovery."""

from pathlib import Path

import pytest
from sqlalchemy import Engine, event, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from tests.m5_helpers import build_workflow_fixture

from storyforge.enums import (
    ChapterStatus,
    ChapterVersionStatus,
    ConflictStatus,
    FactStatus,
    WorkflowEventType,
    WorkflowRunStatus,
)
from storyforge.exceptions import InvalidStateError, WorkflowExecutionError
from storyforge.llm import MockFailure
from storyforge.models import (
    ChapterVersion,
    Conflict,
    Evaluation,
    Fact,
    Revision,
    VersionComparison,
    WorkflowEvent,
    WorkflowRun,
)
from storyforge.repositories import ChapterRepository
from storyforge.schemas.context import ContextBuildRequest
from storyforge.services import ContextBuilder
from storyforge.workflows import ChapterWorkflowRequest


def test_one_pass_accepts_version_and_promotes_only_its_facts(
    db_engine: Engine, tmp_path: Path
) -> None:
    factory, project, provider, service = build_workflow_fixture(
        db_engine, tmp_path / "pass.checkpoints.sqlite3", "pass"
    )

    result = service.run(ChapterWorkflowRequest(project_id=project.id, chapter_number=1))

    assert result.status is WorkflowRunStatus.COMPLETED
    assert result.accepted_version == 1
    assert result.revision_attempt == 0
    assert result.latest_score == pytest.approx(8.46)
    with factory() as session:
        chapter = ChapterRepository(session).get_by_number(project.id, 1)
        assert chapter is not None
        assert chapter.status is ChapterStatus.ACCEPTED
        assert chapter.accepted_version_id == result.accepted_version_id
        version = session.get(ChapterVersion, result.accepted_version_id)
        assert version is not None
        assert version.status is ChapterVersionStatus.ACCEPTED
        evaluation = session.scalar(
            select(Evaluation).where(Evaluation.workflow_run_id == result.workflow_run_id)
        )
        assert evaluation is not None
        assert evaluation.chapter_version_id == version.id
        fact = session.scalar(select(Fact).where(Fact.workflow_run_id == result.workflow_run_id))
        assert fact is not None and fact.status is FactStatus.ACCEPTED
        event_types = set(
            session.scalars(
                select(WorkflowEvent.event_type).where(
                    WorkflowEvent.workflow_run_id == result.workflow_run_id
                )
            )
        )
        assert {
            WorkflowEventType.VERSION_CREATED,
            WorkflowEventType.EVALUATION_CREATED,
            WorkflowEventType.VERSION_ACCEPTED,
            WorkflowEventType.WORKFLOW_COMPLETED,
        } <= event_types
    context = ContextBuilder(factory).build(
        ContextBuildRequest(project_id=project.id, chapter_number=2)
    )
    assert [item.object for item in context.known_facts] == ["brass key"]
    assert provider.call_count == 4  # plan, writer, extraction, critic


def test_revision_improves_and_preserves_immutable_history(
    db_engine: Engine, tmp_path: Path
) -> None:
    factory, project, _, service = build_workflow_fixture(
        db_engine, tmp_path / "improve.checkpoints.sqlite3", "improve"
    )

    result = service.run(
        ChapterWorkflowRequest(
            project_id=project.id,
            chapter_number=1,
            max_revision_attempts=2,
        )
    )

    assert result.status is WorkflowRunStatus.COMPLETED
    assert (result.original_version, result.accepted_version, result.best_version) == (1, 2, 2)
    assert result.revision_attempt == 1
    with factory() as session:
        versions = list(
            session.scalars(
                select(ChapterVersion)
                .where(ChapterVersion.chapter_id == result.chapter_id)
                .order_by(ChapterVersion.version)
            )
        )
        assert [item.version for item in versions] == [1, 2]
        assert [item.status for item in versions] == [
            ChapterVersionStatus.REJECTED,
            ChapterVersionStatus.ACCEPTED,
        ]
        assert versions[1].parent_version_id == versions[0].id
        evaluations = list(
            session.scalars(
                select(Evaluation)
                .where(Evaluation.workflow_run_id == result.workflow_run_id)
                .order_by(Evaluation.id)
            )
        )
        assert [item.chapter_version_id for item in evaluations] == [
            versions[0].id,
            versions[1].id,
        ]
        assert evaluations[1].overall_score > evaluations[0].overall_score
        comparison = session.scalar(
            select(VersionComparison).where(
                VersionComparison.workflow_run_id == result.workflow_run_id
            )
        )
        assert comparison is not None
        assert comparison.decision == "accept_new"
        assert "CRITIC_FLAT_PROSE" in comparison.resolved_issue_codes
        conflict = session.scalar(
            select(Conflict).where(Conflict.evaluation_id == evaluations[0].id)
        )
        assert conflict is not None
        assert conflict.chapter_version_id == versions[0].id
        assert conflict.status is ConflictStatus.RESOLVED
        revision = session.scalar(
            select(Revision).where(Revision.workflow_run_id == result.workflow_run_id)
        )
        assert revision is not None and revision.accepted is True
        facts = list(
            session.scalars(
                select(Fact)
                .where(Fact.workflow_run_id == result.workflow_run_id)
                .order_by(Fact.chapter_version_id)
            )
        )
        assert [item.status for item in facts] == [FactStatus.REJECTED, FactStatus.ACCEPTED]


def test_max_attempts_keeps_best_version_and_isolates_rejected_facts(
    db_engine: Engine, tmp_path: Path
) -> None:
    factory, project, _, service = build_workflow_fixture(
        db_engine, tmp_path / "stagnate.checkpoints.sqlite3", "stagnate"
    )

    result = service.run(
        ChapterWorkflowRequest(
            project_id=project.id,
            chapter_number=1,
            max_revision_attempts=2,
        )
    )

    assert result.status is WorkflowRunStatus.COMPLETED_NEEDS_REVIEW
    assert result.accepted_version is None
    assert result.best_version == 1
    assert result.current_version == 1
    assert result.revision_attempt == 2
    with factory() as session:
        chapter = ChapterRepository(session).get_by_number(project.id, 1)
        assert chapter is not None and chapter.status is ChapterStatus.NEEDS_HUMAN_REVIEW
        versions = list(
            session.scalars(
                select(ChapterVersion)
                .where(ChapterVersion.chapter_id == chapter.id)
                .order_by(ChapterVersion.version)
            )
        )
        assert [item.status for item in versions] == [
            ChapterVersionStatus.NEEDS_REVIEW,
            ChapterVersionStatus.REJECTED,
            ChapterVersionStatus.REJECTED,
        ]
        facts = list(
            session.scalars(select(Fact).where(Fact.workflow_run_id == result.workflow_run_id))
        )
        assert facts and all(item.status is FactStatus.REJECTED for item in facts)
    context = ContextBuilder(factory).build(
        ContextBuildRequest(project_id=project.id, chapter_number=2)
    )
    assert context.known_facts == []


@pytest.mark.parametrize(
    ("pause_after", "expected_counts"),
    [
        ("generate_draft", (1, 0, 0)),
        ("extract_facts", (1, 0, 1)),
        ("evaluate_draft", (1, 1, 1)),
        ("decide_after_evaluation", (1, 1, 1)),
    ],
)
def test_checkpoint_resume_replays_without_duplicate_side_effects(
    db_engine: Engine,
    tmp_path: Path,
    pause_after: str,
    expected_counts: tuple[int, int, int],
) -> None:
    checkpoint = tmp_path / f"{pause_after}.sqlite3"
    factory, project, _, service = build_workflow_fixture(db_engine, checkpoint, "pass")
    paused = service.run(
        ChapterWorkflowRequest(
            project_id=project.id,
            chapter_number=1,
            pause_after=pause_after,
        )
    )
    assert paused.status is WorkflowRunStatus.PAUSED
    assert paused.current_node == pause_after
    with factory() as session:
        counts = (
            session.scalar(
                select(func.count(ChapterVersion.id)).where(
                    ChapterVersion.workflow_run_id == paused.workflow_run_id
                )
            )
            or 0,
            session.scalar(
                select(func.count(Evaluation.id)).where(
                    Evaluation.workflow_run_id == paused.workflow_run_id
                )
            )
            or 0,
            session.scalar(
                select(func.count(Fact.id)).where(Fact.workflow_run_id == paused.workflow_run_id)
            )
            or 0,
        )
    assert counts == expected_counts

    completed = service.resume(paused.workflow_run_id)
    assert completed.status is WorkflowRunStatus.COMPLETED
    with factory() as session:
        assert (
            session.scalar(
                select(func.count(ChapterVersion.id)).where(
                    ChapterVersion.workflow_run_id == paused.workflow_run_id
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count(Evaluation.id)).where(
                    Evaluation.workflow_run_id == paused.workflow_run_id
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count(Fact.id)).where(Fact.workflow_run_id == paused.workflow_run_id)
            )
            == 1
        )
    checkpoint_data = checkpoint.read_bytes()
    assert b"Before sunrise, Mara crossed" not in checkpoint_data
    assert b"sk-" not in checkpoint_data


@pytest.mark.parametrize("pause_after", ["revise_draft", "decide_after_comparison"])
def test_revision_resume_keeps_two_versions_and_evaluations(
    db_engine: Engine, tmp_path: Path, pause_after: str
) -> None:
    factory, project, _, service = build_workflow_fixture(
        db_engine, tmp_path / f"improve-{pause_after}.sqlite3", "improve"
    )
    paused = service.run(
        ChapterWorkflowRequest(
            project_id=project.id,
            chapter_number=1,
            max_revision_attempts=2,
            pause_after=pause_after,
        )
    )
    assert paused.status is WorkflowRunStatus.PAUSED
    completed = service.resume(paused.workflow_run_id)
    assert completed.accepted_version == 2
    with factory() as session:
        assert (
            session.scalar(
                select(func.count(ChapterVersion.id)).where(
                    ChapterVersion.workflow_run_id == paused.workflow_run_id
                )
            )
            == 2
        )
        assert (
            session.scalar(
                select(func.count(Evaluation.id)).where(
                    Evaluation.workflow_run_id == paused.workflow_run_id
                )
            )
            == 2
        )


def test_completed_cannot_resume_and_cancelled_does_not_continue(
    db_engine: Engine, tmp_path: Path
) -> None:
    _, project, _, service = build_workflow_fixture(
        db_engine, tmp_path / "lifecycle.sqlite3", "pass"
    )
    completed = service.run(ChapterWorkflowRequest(project_id=project.id, chapter_number=1))
    with pytest.raises(InvalidStateError, match="paused"):
        service.resume(completed.workflow_run_id)

    factory2, project2, _, service2 = build_workflow_fixture(
        db_engine, tmp_path / "cancel.sqlite3", "pass"
    )
    paused = service2.run(
        ChapterWorkflowRequest(
            project_id=project2.id,
            chapter_number=1,
            pause_after="generate_draft",
        )
    )
    cancelled = service2.cancel(paused.workflow_run_id)
    assert cancelled.status is WorkflowRunStatus.CANCELLED
    with pytest.raises(InvalidStateError, match="paused"):
        service2.resume(paused.workflow_run_id)
    with factory2() as session:
        assert (
            session.get(WorkflowRun, paused.workflow_run_id).status is WorkflowRunStatus.CANCELLED
        )


def test_database_uniqueness_enforces_version_and_fact_idempotency(
    db_engine: Engine, tmp_path: Path
) -> None:
    factory, project, _, service = build_workflow_fixture(
        db_engine, tmp_path / "unique.sqlite3", "pass"
    )
    result = service.run(ChapterWorkflowRequest(project_id=project.id, chapter_number=1))
    with factory() as session:
        original = session.scalar(
            select(ChapterVersion).where(ChapterVersion.workflow_run_id == result.workflow_run_id)
        )
        assert original is not None
        session.add(
            ChapterVersion(
                chapter_id=original.chapter_id,
                version=original.version,
                title="Duplicate",
                content="Duplicate content.",
                summary="Duplicate.",
                status=ChapterVersionStatus.DRAFT,
                source="test",
                idempotency_key="different-key",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_workflow_failure_preserves_previously_accepted_version(
    db_engine: Engine, tmp_path: Path
) -> None:
    factory, project, provider, service = build_workflow_fixture(
        db_engine, tmp_path / "failure.sqlite3", "pass"
    )
    accepted = service.run(ChapterWorkflowRequest(project_id=project.id, chapter_number=1))
    provider.queue_failures([MockFailure.CALL_FAILURE])

    with pytest.raises(WorkflowExecutionError, match="failed safely"):
        service.run(
            ChapterWorkflowRequest(
                project_id=project.id,
                chapter_number=1,
                operation="evaluate_existing",
            )
        )

    with factory() as session:
        chapter = ChapterRepository(session).get_by_number(project.id, 1)
        assert chapter is not None
        assert chapter.status is ChapterStatus.ACCEPTED
        assert chapter.accepted_version_id == accepted.accepted_version_id
        failed = session.scalar(
            select(WorkflowRun)
            .where(WorkflowRun.id != accepted.workflow_run_id)
            .order_by(WorkflowRun.id.desc())
        )
        assert failed is not None
        assert failed.status is WorkflowRunStatus.FAILED
        assert failed.error_code == "EvaluationError"
        assert failed.error_message is not None
        assert "Mock LLM" not in failed.error_message


def test_accept_transaction_failure_rolls_back_version_fact_and_chapter(
    db_engine: Engine, tmp_path: Path
) -> None:
    factory, project, _, service = build_workflow_fixture(
        db_engine, tmp_path / "accept-rollback.sqlite3", "pass"
    )
    paused = service.run(
        ChapterWorkflowRequest(
            project_id=project.id,
            chapter_number=1,
            pause_after="decide_after_evaluation",
        )
    )
    injected = False

    def fail_first_fact_update(
        *args: object,
    ) -> None:
        nonlocal injected
        statement = args[2]
        if not injected and isinstance(statement, str) and statement.startswith("UPDATE facts"):
            injected = True
            raise SQLAlchemyError("forced accept transaction failure")

    event.listen(db_engine, "before_cursor_execute", fail_first_fact_update)
    try:
        with pytest.raises(WorkflowExecutionError, match="resume failed safely"):
            service.resume(paused.workflow_run_id)
    finally:
        event.remove(db_engine, "before_cursor_execute", fail_first_fact_update)

    assert injected is True
    with factory() as session:
        chapter = ChapterRepository(session).get_by_number(project.id, 1)
        assert chapter is not None
        assert chapter.accepted_version_id is None
        assert chapter.status is ChapterStatus.WORKFLOW_FAILED
        version = session.scalar(
            select(ChapterVersion).where(ChapterVersion.workflow_run_id == paused.workflow_run_id)
        )
        fact = session.scalar(select(Fact).where(Fact.workflow_run_id == paused.workflow_run_id))
        run = session.get(WorkflowRun, paused.workflow_run_id)
        assert version is not None and version.status is ChapterVersionStatus.EVALUATED
        assert fact is not None and fact.status is FactStatus.CANDIDATE
        assert run is not None and run.status is WorkflowRunStatus.FAILED
