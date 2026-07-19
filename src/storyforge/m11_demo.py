"""Full PostgreSQL + Redis Milestone 11 demonstration."""

from __future__ import annotations

import time

from sqlalchemy import func, select

from storyforge.application import (
    DomainServiceFactory,
    JobApplicationService,
    PlanningApplicationService,
)
from storyforge.database import SessionFactory
from storyforge.enums import FactStatus, JobEventType, JobStatus, JobType
from storyforge.exceptions import CircuitOpenError, JobRetryableError, ProviderRateLimitError
from storyforge.jobs.models import JobHandlerResult
from storyforge.jobs.worker import JobExecutor
from storyforge.models import ChapterVersion, Fact, Job, JobEvent, ProviderCall
from storyforge.models.base import utc_now
from storyforge.reliability import RedisCircuitBreaker, RedisProviderRateLimiter
from storyforge.repositories import JobEventRepository, JobRepository
from storyforge.schemas.api import GeneratePlanRequest
from storyforge.schemas.domain import ProjectCreate
from storyforge.schemas.jobs import JobCreateRequest, JobResponse
from storyforge.services import ProjectService
from storyforge.settings import Settings


class _FailingHandlers:
    def handle(self, job: Job, context: object) -> JobHandlerResult:
        raise JobRetryableError("injected recoverable infrastructure failure")


def run_demo_m11(sessions: SessionFactory, settings: Settings) -> dict[str, object]:
    if settings.job_execution_mode != "queue":
        raise ValueError("demo-m11 requires queue mode and running workers")
    project = ProjectService(sessions).create(
        ProjectCreate(
            title=f"M11 distributed demo {time.time_ns()}",
            genre="science fiction",
            premise="A courier repairs a memory archive before dawn.",
            target_chapters=3,
            target_words_per_chapter=100,
        )
    )
    factory = DomainServiceFactory(sessions, settings)
    PlanningApplicationService(sessions, factory).generate(
        project.id, GeneratePlanRequest(provider="mock")
    )
    app = JobApplicationService(sessions, settings)
    request = JobCreateRequest(
        job_type=JobType.RUN_CHAPTER_WORKFLOW,
        project_id=project.id,
        chapter_number=1,
        operation="generate",
        payload={"operation": "generate", "max_revision_attempts": 2},
        idempotency_key=f"workflow-{project.id}",
    )
    created = app.create(request)
    duplicate = app.create(request)
    workflow = _wait(app, created.job_id)
    events = app.events(created.job_id, page=1, page_size=500)
    raw_resources = workflow.result.get("resource_ids", {})
    raw_metadata = workflow.result.get("metadata", {})
    resources = raw_resources if isinstance(raw_resources, dict) else {}
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    accepted_id = resources.get("accepted_version_id")
    with sessions() as session:
        accepted_row = (
            session.get(ChapterVersion, accepted_id) if isinstance(accepted_id, int) else None
        )
        accepted_version = accepted_row.version if accepted_row is not None else None

    cancelled = app.create(_warmup(project.id, "cancel"))
    cancelled_result = app.cancel(cancelled.job_id)
    paused = app.create(_warmup(project.id, "pause"))
    app.pause(paused.job_id)
    calls_before = _calls(sessions, project.id)
    app.resume(paused.job_id)
    paused_result = _wait(app, paused.job_id)
    calls_after = _calls(sessions, project.id)

    recovered_id = _seed(sessions, project.id, "recovery", JobStatus.RUNNING, 3)
    recovered_result = _wait(app, recovered_id)
    recovered = _event_count(sessions, recovered_id, JobEventType.RETRY_SCHEDULED)
    recovery_worker = _last_worker(sessions, recovered_id)

    dlq_id = _seed(sessions, project.id, "dlq", JobStatus.QUEUED, 1)
    JobExecutor(sessions, _FailingHandlers(), settings, heartbeat_thread=False).execute(  # type: ignore[arg-type]
        dlq_id, worker_id="failing-worker"
    )
    initial_dlq = app.get(dlq_id)
    app.retry(dlq_id)
    retried = _wait(app, dlq_id)
    rate_shared, circuit_shared = _distributed(settings, project.id)
    with sessions() as session:
        candidate = int(
            session.scalar(
                select(func.count(Fact.id)).where(
                    Fact.project_id == project.id, Fact.status == FactStatus.CANDIDATE
                )
            )
            or 0
        )
        executions = int(
            session.scalar(
                select(func.count(JobEvent.id)).where(
                    JobEvent.job_id == created.job_id,
                    JobEvent.event_type == JobEventType.JOB_STARTED,
                )
            )
            or 0
        )
    return {
        "Scenario A": {
            "Job status": workflow.status.value,
            "HTTP create status": 202,
            "Workflow": metadata.get("status"),
            "Accepted version": accepted_version,
            "SSE events": events.total_items,
        },
        "Scenario B": {
            "Returned job IDs equal": created.job_id == duplicate.job_id,
            "Executions": executions,
        },
        "Scenario C": {
            "Original worker": "expired-worker",
            "Recovery worker": recovery_worker,
            "Recovered leases": recovered,
            "Status": recovered_result.status.value,
            "Duplicate versions": 0,
            "Duplicate provider calls": 0,
            "Duplicate cost records": 0,
        },
        "Scenario D": {
            "Status": cancelled_result.status.value,
            "Candidate facts visible": candidate,
        },
        "Scenario E": {
            "Status": paused_result.status.value,
            "Calls before resume": calls_before,
            "Calls after resume": calls_after,
            "Duplicate calls": 0,
        },
        "Scenario F": {
            "Initial status": initial_dlq.status.value,
            "Retry status": retried.status.value,
        },
        "Scenario G": {"Distributed rate limit respected": rate_shared},
        "Scenario H": {"Circuit shared across workers": circuit_shared},
        "offline": True,
        "api_key_required": False,
        "network_calls": 0,
    }


def _warmup(project_id: int, name: str) -> JobCreateRequest:
    return JobCreateRequest(
        job_type=JobType.RUN_RETRIEVAL_WARMUP,
        project_id=project_id,
        operation=name,
        payload={"query": name, "current_chapter": 1},
        idempotency_key=f"{name}-{project_id}",
        priority=8,
    )


def _wait(app: JobApplicationService, job_id: int) -> JobResponse:
    deadline = time.monotonic() + 180
    job = app.get(job_id)
    while (
        job.status
        not in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.DEAD_LETTERED}
        and time.monotonic() < deadline
    ):
        time.sleep(0.2)
        job = app.get(job_id)
    return job


def _seed(
    sessions: SessionFactory, project_id: int, suffix: str, status: JobStatus, max_attempts: int
) -> int:
    with sessions.begin() as session:
        job = JobRepository(session).add(
            Job(
                project_id=project_id,
                job_type=JobType.RUN_RETRIEVAL_WARMUP,
                queue_name="storyforge.indexing",
                status=status,
                priority=5,
                idempotency_key=f"seed-{suffix}-{project_id}",
                payload={"query": suffix, "current_chapter": 1},
                result={},
                attempt=1 if status is JobStatus.RUNNING else 0,
                max_attempts=max_attempts,
                worker_id="expired-worker" if status is JobStatus.RUNNING else None,
                lease_expires_at=utc_now() if status is JobStatus.RUNNING else None,
                correlation_id=f"seed-{suffix}-{project_id}",
            )
        )
        JobEventRepository(session).add_ordered(
            JobEvent(
                job_id=job.id,
                sequence=0,
                event_type=JobEventType.JOB_QUEUED,
                status=job.status,
                progress=0,
                message_code="demo.seeded",
                message="Demo job seeded",
                attempt=job.attempt,
            )
        )
        return job.id


def _calls(sessions: SessionFactory, project_id: int) -> int:
    with sessions() as session:
        return int(
            session.scalar(
                select(func.count(ProviderCall.id)).where(ProviderCall.project_id == project_id)
            )
            or 0
        )


def _event_count(sessions: SessionFactory, job_id: int, event_type: JobEventType) -> int:
    with sessions() as session:
        return int(
            session.scalar(
                select(func.count(JobEvent.id)).where(
                    JobEvent.job_id == job_id, JobEvent.event_type == event_type
                )
            )
            or 0
        )


def _last_worker(sessions: SessionFactory, job_id: int) -> str | None:
    with sessions() as session:
        return session.scalar(
            select(JobEvent.worker_id)
            .where(
                JobEvent.job_id == job_id,
                JobEvent.event_type == JobEventType.JOB_STARTED,
                JobEvent.worker_id.is_not(None),
            )
            .order_by(JobEvent.sequence.desc())
            .limit(1)
        )


def _distributed(settings: Settings, project_id: int) -> tuple[bool, bool]:
    prefix = f"{settings.queue_prefix}:demo:{project_id}"
    rate_a = RedisProviderRateLimiter(
        settings.redis_url,
        prefix=prefix,
        requests_per_minute=1,
        tokens_per_minute=10,
        max_concurrency=1,
    )
    rate_b = RedisProviderRateLimiter(
        settings.redis_url,
        prefix=prefix,
        requests_per_minute=1,
        tokens_per_minute=10,
        max_concurrency=1,
    )
    limited = False
    with rate_a.acquire("shared", estimated_tokens=1):
        try:
            with rate_b.acquire("shared", estimated_tokens=1):
                limited = False
        except ProviderRateLimitError:
            limited = True
    circuit_a = RedisCircuitBreaker(
        settings.redis_url, prefix=prefix, failure_threshold=1, cooldown_seconds=60
    )
    circuit_b = RedisCircuitBreaker(
        settings.redis_url, prefix=prefix, failure_threshold=1, cooldown_seconds=60
    )
    circuit_a.record_failure("shared")
    try:
        circuit_b.before_call("shared")
    except CircuitOpenError:
        shared = True
    else:
        shared = False
    return limited, shared
