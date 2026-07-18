"""Workflow-level hard-budget handling preserves durable progress."""

from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from tests.m5_helpers import build_workflow_fixture

from storyforge.enums import ChapterStatus, FactStatus, WorkflowRunStatus
from storyforge.exceptions import BudgetBlockedError
from storyforge.models import Fact
from storyforge.repositories import ChapterRepository
from storyforge.workflows import ChapterWorkflowRequest


def test_budget_block_during_revision_preserves_best_version_for_review(
    db_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory, project, _, service = build_workflow_fixture(
        db_engine,
        tmp_path / "budget-block.checkpoints.sqlite3",
        "improve",
    )
    paused = service.run(
        ChapterWorkflowRequest(
            project_id=project.id,
            chapter_number=1,
            max_revision_attempts=2,
            pause_after="build_revision_brief",
        )
    )
    assert paused.status is WorkflowRunStatus.PAUSED
    assert paused.best_version_id is not None

    def block_revision(**_: object) -> object:
        raise BudgetBlockedError("Workflow hard budget was reached")

    monkeypatch.setattr(service._versions, "revise", block_revision)
    result = service.resume(paused.workflow_run_id)

    assert result.status is WorkflowRunStatus.COMPLETED_NEEDS_REVIEW
    assert result.best_version_id == paused.best_version_id
    assert result.current_version_id == paused.best_version_id
    assert result.accepted_version_id is None
    assert "budget_blocked" in result.blocking_reasons
    assert result.error_code == "BudgetBlockedError"
    with factory() as session:
        chapter = ChapterRepository(session).get(result.chapter_id)
        assert chapter is not None
        assert chapter.status is ChapterStatus.NEEDS_HUMAN_REVIEW
        candidate_count = session.scalar(
            select(Fact.id).where(
                Fact.workflow_run_id == result.workflow_run_id,
                Fact.status == FactStatus.CANDIDATE,
            )
        )
        assert candidate_count is None
