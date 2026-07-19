"""Allowlisted Job handlers that only adapt to existing application services."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, cast

from sqlalchemy.orm import Session

from storyforge.application import (
    BookWorkflowApplicationService,
    ChapterApplicationService,
    EvaluationApplicationService,
    MemoryApplicationService,
    PlanningApplicationService,
)
from storyforge.application.factory import DomainServiceFactory
from storyforge.database import SessionFactory
from storyforge.enums import JobEventType, JobStatus, JobType, WorkflowRunStatus
from storyforge.exceptions import JobCancellationRequested, JobPauseRequested
from storyforge.jobs.models import JobHandlerResult
from storyforge.models import Job
from storyforge.repositories import JobRepository
from storyforge.schemas.api import (
    EvaluateChapterRequest,
    GenerateChapterRequest,
    GeneratePlanRequest,
    MemoryReindexRequest,
    RetrievalSearchRequest,
)
from storyforge.services.book_runs import BookRunService
from storyforge.services.jobs import JobService
from storyforge.settings import Settings
from storyforge.workflows import ChapterWorkflowRequest


class JobExecutionContext:
    """Safe progress/control boundary injected into a handler."""

    def __init__(
        self,
        session_factory: SessionFactory,
        service: JobService,
        job_id: int,
    ) -> None:
        self._session_factory = session_factory
        self._service = service
        self.job_id = job_id

    def check_control(self, step: str) -> None:
        with self._session_factory() as session:
            job = JobRepository(session).get(self.job_id)
            if job is None:
                raise JobCancellationRequested("Job disappeared during execution")
            if job.status is JobStatus.CANCEL_REQUESTED:
                raise JobCancellationRequested("Cancellation requested")
            if job.status is JobStatus.PAUSE_REQUESTED:
                raise JobPauseRequested("Pause requested")
        self._service.record_event(
            self.job_id,
            JobEventType.WORKFLOW_NODE_STARTED,
            code="workflow.node_started",
            message="Workflow node started",
            step=step,
            progress=_workflow_progress(step),
        )

    def workflow_progress(self, phase: str, step: str) -> None:
        if phase != "completed":
            return
        event_type = (
            JobEventType.WORKFLOW_NODE_COMPLETED
            if phase == "completed"
            else JobEventType.WORKFLOW_NODE_STARTED
        )
        self._service.record_event(
            self.job_id,
            event_type,
            code=f"workflow.node_{phase}",
            message=f"Workflow node {phase}",
            step=step,
            progress=_workflow_progress(step) + (2 if phase == "completed" else 0),
        )


class JobHandlers:
    """Compile-time handler map; payloads never select a Python import path."""

    def __init__(
        self,
        session_factory: SessionFactory,
        factory: DomainServiceFactory,
        settings: Settings,
        job_service: JobService,
    ) -> None:
        self._session_factory = session_factory
        self._factory = factory
        self._settings = settings
        self._jobs = job_service
        self._handlers: dict[JobType, Callable[[Job, JobExecutionContext], JobHandlerResult]] = {
            JobType.GENERATE_PLAN: self._generate_plan,
            JobType.GENERATE_CHAPTER: self._generate_chapter,
            JobType.EVALUATE_CHAPTER: self._evaluate_chapter,
            JobType.RUN_CHAPTER_WORKFLOW: self._run_workflow,
            JobType.RESUME_WORKFLOW: self._resume_workflow,
            JobType.REINDEX_MEMORY: self._reindex_memory,
            JobType.RUN_RETRIEVAL_WARMUP: self._retrieval_warmup,
            JobType.RUN_BOOK: self._run_book,
            JobType.RESUME_BOOK: self._run_book,
        }

    def handle(self, job: Job, context: JobExecutionContext) -> JobHandlerResult:
        return self._handlers[job.job_type](job, context)

    def _generate_plan(self, job: Job, context: JobExecutionContext) -> JobHandlerResult:
        context.check_control("generate_plan")
        response = PlanningApplicationService(self._session_factory, self._factory).generate(
            _required_project(job),
            GeneratePlanRequest(replace_existing=bool(job.payload.get("replace_existing", False))),
        )
        return JobHandlerResult(
            resource_ids={"project_id": response.project_id},
            summary="Plan generated",
            metadata={"chapters": len(response.chapter_plans)},
        )

    def _generate_chapter(self, job: Job, context: JobExecutionContext) -> JobHandlerResult:
        context.check_control("generate_chapter")
        response = ChapterApplicationService(
            self._session_factory, self._factory, self._settings
        ).generate(
            _required_project(job),
            _chapter_number(job),
            GenerateChapterRequest(
                regenerate=bool(job.payload.get("regenerate", False)),
                max_context_chars=int(job.payload.get("max_context_chars", 24_000)),
            ),
        )
        return JobHandlerResult(
            resource_ids={"chapter_id": response.chapter_id},
            summary="Chapter generated",
            metadata={"version": response.version, "fact_count": response.fact_count},
        )

    def _evaluate_chapter(self, job: Job, context: JobExecutionContext) -> JobHandlerResult:
        context.check_control("evaluate_chapter")
        response = EvaluationApplicationService(self._session_factory, self._factory).evaluate(
            _required_project(job),
            _chapter_number(job),
            EvaluateChapterRequest(
                force_new_version=bool(job.payload.get("force_new_version", True))
            ),
        )
        return JobHandlerResult(
            resource_ids={"evaluation_id": response.id},
            summary="Chapter evaluated",
            metadata={"final_score": response.final_score, "passed": response.passed},
        )

    def _run_workflow(self, job: Job, context: JobExecutionContext) -> JobHandlerResult:
        context.check_control("initialize_workflow")
        with self._factory.provider(
            "workflow",
            project_id=_required_project(job),
            chapter_number=_chapter_number(job),
        ) as provider:
            service = self._factory.workflow_service(
                provider,
                control_callback=context.check_control,
                progress_callback=context.workflow_progress,
                initialized_callback=lambda session, workflow_run_id: (
                    self._link_workflow_in_session(session, job.id, workflow_run_id)
                ),
            )
            if job.workflow_run_id is not None:
                result = service.resume(job.workflow_run_id)
            else:
                result = service.run(
                    ChapterWorkflowRequest(
                        project_id=_required_project(job),
                        chapter_number=_chapter_number(job),
                        operation=cast(
                            Literal["generate", "evaluate_existing"],
                            str(job.payload.get("operation", "generate")),
                        ),
                        max_revision_attempts=int(
                            job.payload.get(
                                "max_revision_attempts", self._settings.max_revision_attempts
                            )
                        ),
                        pause_after=(
                            str(job.payload["pause_after"])
                            if job.payload.get("pause_after")
                            else None
                        ),
                    )
                )
        self._link_workflow(job.id, result.workflow_run_id)
        if result.status is WorkflowRunStatus.PAUSED:
            raise JobPauseRequested("Workflow paused at a safe node")
        if result.status is WorkflowRunStatus.CANCELLED:
            raise JobCancellationRequested("Workflow cancelled at a safe node")
        return JobHandlerResult(
            resource_ids={
                "workflow_run_id": result.workflow_run_id,
                "accepted_version_id": result.accepted_version_id,
                "best_version_id": result.best_version_id,
            },
            summary="Chapter workflow completed",
            metadata={
                "status": result.status.value,
                "revision_attempt": result.revision_attempt,
                "latest_score": result.latest_score,
            },
        )

    def _resume_workflow(self, job: Job, context: JobExecutionContext) -> JobHandlerResult:
        if job.workflow_run_id is None:
            raise ValueError("Resume workflow job requires workflow_run_id")
        return self._run_workflow(job, context)

    def _reindex_memory(self, job: Job, context: JobExecutionContext) -> JobHandlerResult:
        context.check_control("reindex_memory")
        response = MemoryApplicationService(
            self._session_factory, self._factory, self._settings
        ).reindex(
            _required_project(job),
            MemoryReindexRequest.model_validate(job.payload),
        )
        return JobHandlerResult(
            resource_ids={"project_id": response.project_id},
            summary="Memory reindexed",
            metadata={"indexed_versions": len(response.results)},
        )

    def _retrieval_warmup(self, job: Job, context: JobExecutionContext) -> JobHandlerResult:
        context.check_control("retrieval_warmup")
        response = MemoryApplicationService(
            self._session_factory, self._factory, self._settings
        ).search(
            _required_project(job),
            RetrievalSearchRequest.model_validate(job.payload),
        )
        return JobHandlerResult(
            resource_ids={"project_id": _required_project(job)},
            summary="Retrieval warmup completed",
            metadata={"hit_count": len(response.hits), "degraded": response.degraded},
        )

    def _run_book(self, job: Job, context: JobExecutionContext) -> JobHandlerResult:
        run_id = job.book_run_id or _positive_payload_id(job, "book_run_id")
        runs = BookRunService(self._session_factory, self._settings)
        context.check_control("initialize_book_run")
        try:
            result = BookWorkflowApplicationService(
                self._session_factory, self._factory, self._settings
            ).execute(
                run_id,
                control_callback=context.check_control,
                progress_callback=context.workflow_progress,
            )
        except JobPauseRequested:
            runs.mark_paused(run_id)
            raise
        except JobCancellationRequested:
            runs.mark_cancelled(run_id)
            raise
        except Exception as exc:
            runs.mark_failed(run_id, exc)
            raise
        snapshot_value = result.get("snapshot_id")
        snapshot_id = snapshot_value if isinstance(snapshot_value, int) else None
        return JobHandlerResult(
            resource_ids={
                "book_run_id": run_id,
                "snapshot_id": snapshot_id,
            },
            summary="Book workflow completed",
            metadata=result,
        )

    def _link_workflow(self, job_id: int, workflow_run_id: int) -> None:
        with self._session_factory.begin() as session:
            self._link_workflow_in_session(session, job_id, workflow_run_id)

    @staticmethod
    def _link_workflow_in_session(session: Session, job_id: int, workflow_run_id: int) -> None:
        job = JobRepository(session).get_for_update(job_id)
        if job is not None and job.workflow_run_id is None:
            job.workflow_run_id = workflow_run_id


def _required_project(job: Job) -> int:
    if job.project_id is None:
        raise ValueError("Job requires project_id")
    return job.project_id


def _chapter_number(job: Job) -> int:
    value = job.payload.get("chapter_number")
    if not isinstance(value, int) or value <= 0:
        raise ValueError("Job requires a positive chapter_number")
    return value


def _positive_payload_id(job: Job, field: str) -> int:
    value = job.payload.get(field)
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"Job requires a positive {field}")
    return value


def _workflow_progress(node: str) -> int:
    order = (
        "initialize_workflow",
        "load_context",
        "generate_draft",
        "extract_facts",
        "evaluate_draft",
        "decide_after_evaluation",
        "build_revision_brief",
        "revise_draft",
        "extract_revision_facts",
        "evaluate_revision",
        "compare_versions",
        "decide_after_comparison",
        "accept_version",
        "mark_needs_human_review",
    )
    try:
        index = order.index(node)
    except ValueError:
        return 5
    return min(95, 5 + round(index / max(1, len(order) - 1) * 88))
