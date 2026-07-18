"""Synchronous workflow start, resume, cancellation, and audit queries."""

from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from storyforge.database import SessionFactory
from storyforge.enums import WorkflowRunStatus
from storyforge.exceptions import DomainValidationError, EntityNotFoundError
from storyforge.repositories import (
    ProjectRepository,
    WorkflowEventRepository,
    WorkflowRunRepository,
)
from storyforge.schemas.api import (
    PageResponse,
    StartWorkflowRequest,
    WorkflowEventResponse,
    WorkflowOperation,
    WorkflowStatusResponse,
)
from storyforge.settings import Settings
from storyforge.workflows import ChapterWorkflowRequest, WorkflowStatusResult

from .common import page_response
from .factory import DomainServiceFactory


class WorkflowApplicationService:
    """Adapt the durable synchronous workflow without exposing checkpoints."""

    def __init__(
        self,
        session_factory: SessionFactory,
        factory: DomainServiceFactory,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._factory = factory
        self._settings = settings

    def start(
        self, project_id: int, chapter_number: int, request: StartWorkflowRequest
    ) -> WorkflowStatusResponse:
        if request.pause_after_node is not None and not self._settings.allow_debug_pause_nodes:
            raise DomainValidationError(
                "pause_after_node is disabled outside an explicitly configured debug run"
            )
        operation: Literal["generate", "evaluate_existing"] = (
            "generate"
            if request.operation is WorkflowOperation.GENERATE_EVALUATE_REVISE
            else "evaluate_existing"
        )
        with self._factory.provider(
            "workflow",
            project_id=project_id,
            chapter_number=chapter_number,
            override=request.provider,
        ) as provider:
            result = self._factory.workflow_service(provider).run(
                ChapterWorkflowRequest(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    operation=operation,
                    max_revision_attempts=request.max_revision_attempts,
                    pause_after=request.pause_after_node,
                )
            )
        return _workflow_status(result)

    def get(self, workflow_run_id: int) -> WorkflowStatusResponse:
        project_id, chapter_number = self._workflow_scope(workflow_run_id)
        with self._factory.provider(
            "workflow", project_id=project_id, chapter_number=chapter_number
        ) as provider:
            return _workflow_status(
                self._factory.workflow_service(provider).get_status(workflow_run_id)
            )

    def resume(self, workflow_run_id: int) -> WorkflowStatusResponse:
        project_id, chapter_number = self._workflow_scope(workflow_run_id)
        with self._factory.provider(
            "workflow", project_id=project_id, chapter_number=chapter_number
        ) as provider:
            return _workflow_status(
                self._factory.workflow_service(provider).resume(workflow_run_id)
            )

    def cancel(self, workflow_run_id: int) -> WorkflowStatusResponse:
        project_id, chapter_number = self._workflow_scope(workflow_run_id)
        with self._factory.provider(
            "workflow", project_id=project_id, chapter_number=chapter_number
        ) as provider:
            return _workflow_status(
                self._factory.workflow_service(provider).cancel(workflow_run_id)
            )

    def list_events(
        self, workflow_run_id: int, *, page: int, page_size: int
    ) -> PageResponse[WorkflowEventResponse]:
        with self._session_factory() as session:
            if WorkflowRunRepository(session).get(workflow_run_id) is None:
                raise EntityNotFoundError(f"Workflow run {workflow_run_id} was not found")
            result = WorkflowEventRepository(session).page_for_run(
                workflow_run_id, page=page, page_size=page_size
            )
            items = [
                WorkflowEventResponse(
                    id=item.id,
                    node=item.node,
                    event_type=item.event_type,
                    attempt=item.attempt,
                    status=item.status,
                    duration_ms=item.duration_ms,
                    version_id=item.version_id,
                    evaluation_id=item.evaluation_id,
                    error_code=item.error_code,
                    created_at=item.created_at,
                )
                for item in result.items
            ]
        return page_response(result, page=page, page_size=page_size, items=items)

    def list_project_runs(
        self, project_id: int, *, page: int, page_size: int
    ) -> PageResponse[WorkflowStatusResponse]:
        with self._session_factory() as session:
            self._require_project(session, project_id)
            result = WorkflowRunRepository(session).page_for_project(
                project_id, page=page, page_size=page_size
            )
            items = [self._status_from_repository(item.id) for item in result.items]
        return page_response(result, page=page, page_size=page_size, items=items)

    def _status_from_repository(self, workflow_run_id: int) -> WorkflowStatusResponse:
        project_id, chapter_number = self._workflow_scope(workflow_run_id)
        with self._factory.provider(
            "workflow", project_id=project_id, chapter_number=chapter_number
        ) as provider:
            result = self._factory.workflow_service(provider).get_status(workflow_run_id)
        return _workflow_status(result)

    def _workflow_scope(self, workflow_run_id: int) -> tuple[int, int]:
        with self._session_factory() as session:
            workflow = WorkflowRunRepository(session).get(workflow_run_id)
            if workflow is None:
                raise EntityNotFoundError(f"Workflow run {workflow_run_id} was not found")
            return workflow.project_id, workflow.chapter.chapter_number

    @staticmethod
    def _require_project(session: Session, project_id: int) -> None:
        if ProjectRepository(session).get(project_id) is None:
            raise EntityNotFoundError(f"Project {project_id} was not found")


def _workflow_status(result: WorkflowStatusResult) -> WorkflowStatusResponse:
    return WorkflowStatusResponse(
        workflow_run_id=result.workflow_run_id,
        thread_id=result.thread_id,
        project_id=result.project_id,
        chapter_id=result.chapter_id,
        chapter_number=result.chapter_number,
        current_node=result.current_node,
        status=result.status,
        original_version_id=result.original_version_id,
        current_version_id=result.current_version_id,
        best_version_id=result.best_version_id,
        accepted_version_id=result.accepted_version_id,
        original_version=result.original_version,
        current_version=result.current_version,
        best_version=result.best_version,
        accepted_version=result.accepted_version,
        revision_attempt=result.revision_attempt,
        max_revision_attempts=result.max_revision_attempts,
        latest_score=result.latest_score,
        blocking_reasons=list(result.blocking_reasons),
        error_code=result.error_code,
        error_message=result.error_message,
        started_at=result.started_at,
        updated_at=result.updated_at,
        finished_at=result.finished_at,
    )


def is_terminal_workflow(status: WorkflowRunStatus) -> bool:
    """Return whether status represents a finished public workflow."""
    return status in {
        WorkflowRunStatus.COMPLETED,
        WorkflowRunStatus.COMPLETED_NEEDS_REVIEW,
        WorkflowRunStatus.FAILED,
        WorkflowRunStatus.CANCELLED,
    }
