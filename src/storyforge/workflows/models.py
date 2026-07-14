"""Public request and status models for the durable workflow service."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from storyforge.enums import WorkflowRunStatus
from storyforge.schemas.base import EntityId, NonNegativeInt, PositiveInt, RequestModel


class ChapterWorkflowRequest(RequestModel):
    """Start one generation/evaluation/revision workflow."""

    project_id: EntityId
    chapter_number: PositiveInt
    operation: Literal["generate", "evaluate_existing"] = "generate"
    max_revision_attempts: NonNegativeInt = Field(default=2, le=10)
    pause_after: str | None = Field(default=None, max_length=100)


class WorkflowStatusResult(RequestModel):
    """Small, user-facing projection of a WorkflowRun."""

    workflow_run_id: EntityId
    thread_id: str
    project_id: EntityId
    chapter_id: EntityId
    chapter_number: PositiveInt
    current_node: str
    status: WorkflowRunStatus
    original_version_id: EntityId | None = None
    current_version_id: EntityId | None = None
    best_version_id: EntityId | None = None
    accepted_version_id: EntityId | None = None
    original_version: PositiveInt | None = None
    current_version: PositiveInt | None = None
    best_version: PositiveInt | None = None
    accepted_version: PositiveInt | None = None
    revision_attempt: NonNegativeInt
    max_revision_attempts: NonNegativeInt
    latest_score: float | None = Field(default=None, ge=0, le=10)
    blocking_reasons: list[str] = Field(default_factory=list)
    node_history: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None
