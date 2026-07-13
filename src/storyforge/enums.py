"""Shared domain enumerations used by persistence and boundary schemas."""

from enum import StrEnum


class ProjectStatus(StrEnum):
    """Lifecycle status for a story project."""

    DRAFT = "draft"
    PLANNING = "planning"
    PLANNED = "planned"
    GENERATING = "generating"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class ChapterStatus(StrEnum):
    """Lifecycle status for a chapter."""

    PLANNED = "planned"
    GENERATING = "generating"
    DRAFT = "draft"
    EXTRACTING_FACTS = "extracting_facts"
    GENERATED = "generated"
    FACT_EXTRACTION_FAILED = "fact_extraction_failed"
    FAILED = "failed"
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
