"""Serializable state contract stored by the LangGraph checkpointer."""

from typing import TypedDict


class WorkflowErrorState(TypedDict):
    """Small, redacted error entry safe for checkpoints."""

    code: str
    message: str
    node: str


class ChapterWorkflowState(TypedDict, total=False):
    """Only IDs and small DTOs; never sessions, clients, secrets, or ORM objects."""

    thread_id: str
    workflow_run_id: int
    project_id: int
    chapter_id: int
    chapter_number: int
    operation: str
    current_node: str
    status: str
    original_version_id: int | None
    current_version_id: int | None
    best_version_id: int | None
    accepted_version_id: int | None
    comparison_base_version_id: int | None
    current_evaluation_id: int | None
    current_evaluation: dict[str, object]
    revision_brief: dict[str, object]
    comparison: dict[str, object]
    revision_attempt: int
    max_revision_attempts: int
    node_history: list[str]
    errors: list[WorkflowErrorState]
    blocking_reasons: list[str]
    route: str
    started_at: str
    updated_at: str
