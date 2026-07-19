"""Static registry for supported asynchronous operations."""

from __future__ import annotations

from storyforge.enums import JobType
from storyforge.jobs.models import JobDefinition

_DEFINITIONS = {
    definition.job_type: definition
    for definition in (
        JobDefinition(
            job_type=JobType.GENERATE_PLAN,
            handler_name="generate_plan",
            queue_name="storyforge.default",
            max_attempts=3,
            timeout_seconds=900,
            retry_policy="infrastructure_only",
            cancellable=True,
            resumable=False,
            idempotent=True,
        ),
        JobDefinition(
            job_type=JobType.GENERATE_CHAPTER,
            handler_name="generate_chapter",
            queue_name="storyforge.default",
            max_attempts=3,
            timeout_seconds=1800,
            retry_policy="infrastructure_only",
            cancellable=True,
            resumable=False,
            idempotent=True,
        ),
        JobDefinition(
            job_type=JobType.EVALUATE_CHAPTER,
            handler_name="evaluate_chapter",
            queue_name="storyforge.default",
            max_attempts=3,
            timeout_seconds=1800,
            retry_policy="infrastructure_only",
            cancellable=True,
            resumable=False,
            idempotent=True,
        ),
        JobDefinition(
            job_type=JobType.RUN_CHAPTER_WORKFLOW,
            handler_name="run_chapter_workflow",
            queue_name="storyforge.workflow",
            max_attempts=3,
            timeout_seconds=7200,
            retry_policy="infrastructure_only",
            cancellable=True,
            resumable=True,
            idempotent=True,
        ),
        JobDefinition(
            job_type=JobType.RESUME_WORKFLOW,
            handler_name="resume_workflow",
            queue_name="storyforge.workflow",
            max_attempts=3,
            timeout_seconds=7200,
            retry_policy="infrastructure_only",
            cancellable=True,
            resumable=True,
            idempotent=True,
        ),
        JobDefinition(
            job_type=JobType.REINDEX_MEMORY,
            handler_name="reindex_memory",
            queue_name="storyforge.indexing",
            max_attempts=4,
            timeout_seconds=3600,
            retry_policy="provider_or_infrastructure",
            cancellable=True,
            resumable=False,
            idempotent=True,
        ),
        JobDefinition(
            job_type=JobType.RUN_RETRIEVAL_WARMUP,
            handler_name="run_retrieval_warmup",
            queue_name="storyforge.indexing",
            max_attempts=2,
            timeout_seconds=600,
            retry_policy="infrastructure_only",
            cancellable=True,
            resumable=False,
            idempotent=True,
        ),
        JobDefinition(
            job_type=JobType.RUN_BOOK,
            handler_name="run_book",
            queue_name="storyforge.book",
            max_attempts=3,
            timeout_seconds=86_400,
            retry_policy="infrastructure_only",
            cancellable=True,
            resumable=True,
            idempotent=True,
        ),
        JobDefinition(
            job_type=JobType.RESUME_BOOK,
            handler_name="resume_book",
            queue_name="storyforge.book",
            max_attempts=3,
            timeout_seconds=86_400,
            retry_policy="infrastructure_only",
            cancellable=True,
            resumable=True,
            idempotent=True,
        ),
    )
}


class JobRegistry:
    """Resolve only compile-time registered job types; never dynamic-import input."""

    def get(self, job_type: JobType) -> JobDefinition:
        return _DEFINITIONS[job_type]

    def list(self) -> tuple[JobDefinition, ...]:
        return tuple(_DEFINITIONS[item] for item in JobType)
