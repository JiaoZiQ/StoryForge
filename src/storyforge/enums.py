"""Shared domain enumerations used by persistence and boundary schemas."""

from enum import StrEnum


class ProjectStatus(StrEnum):
    """Lifecycle status for a story project."""

    DRAFT = "draft"
    PLANNING = "planning"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ChapterStatus(StrEnum):
    """Lifecycle status for a chapter."""

    PLANNED = "planned"
    DRAFT = "draft"
    EVALUATING = "evaluating"
    NEEDS_REVISION = "needs_revision"
    ACCEPTED = "accepted"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class ForeshadowingStatus(StrEnum):
    """Lifecycle status for a foreshadowing setup."""

    PLANNED = "planned"
    OPEN = "open"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


class WorkflowRunStatus(StrEnum):
    """Execution status for a persisted workflow run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
