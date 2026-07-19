"""Transactional job admission, controls, and durable event recording."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from storyforge.database import SessionFactory
from storyforge.enums import (
    ChapterStatus,
    JobEventType,
    JobStatus,
    JobType,
    OutboxStatus,
    WorkflowRunStatus,
)
from storyforge.exceptions import (
    DomainValidationError,
    EntityNotFoundError,
    InvalidStateError,
    QueueBackpressureError,
    QueueUnavailableError,
)
from storyforge.jobs.broker import RedisEventBus
from storyforge.jobs.models import JobCreationResult, normalized_payload
from storyforge.jobs.registry import JobRegistry
from storyforge.jobs.transitions import transition_job
from storyforge.models import Job, JobEvent, OutboxMessage
from storyforge.models.base import utc_now
from storyforge.privacy.redaction import RedactionService
from storyforge.repositories import (
    ChapterRepository,
    JobEventRepository,
    JobRepository,
    OutboxRepository,
    ProjectRepository,
    WorkflowRunRepository,
)
from storyforge.settings import Settings
from storyforge.workflows.transitions import transition_workflow

_SENSITIVE_KEYS = frozenset(
    {"api_key", "authorization", "password", "secret", "token", "database_url", "content"}
)
logger = logging.getLogger(__name__)


class JobService:
    """Own all Job transactions; adapters never mutate ORM rows directly."""

    def __init__(
        self,
        session_factory: SessionFactory,
        settings: Settings,
        *,
        registry: JobRegistry | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._registry = registry or JobRegistry()
        self._redaction = RedactionService()
        self._event_bus = (
            RedisEventBus(settings.redis_url, prefix=settings.queue_prefix)
            if settings.job_execution_mode == "queue"
            else None
        )

    def create(
        self,
        *,
        job_type: JobType,
        project_id: int | None,
        chapter_id: int | None,
        workflow_run_id: int | None,
        payload: dict[str, object],
        operation: str,
        external_idempotency_key: str | None = None,
        priority: int = 5,
        correlation_id: str | None = None,
    ) -> JobCreationResult:
        """Atomically create one Job, one JobEvent, and one pending Outbox row."""
        definition = self._registry.get(job_type)
        normalized = normalized_payload(payload)
        self._validate_payload(normalized)
        idempotency_key = self._idempotency_key(
            job_type=job_type,
            project_id=project_id,
            chapter_id=chapter_id,
            workflow_run_id=workflow_run_id,
            operation=operation,
            payload=normalized,
            external_key=external_idempotency_key,
        )
        with self._session_factory() as lookup_session:
            existing = JobRepository(lookup_session).get_by_idempotency_key(idempotency_key)
            if existing is not None:
                return JobCreationResult(job_id=existing.id, reused=True)
        try:
            with self._session_factory.begin() as session:
                repository = JobRepository(session)
                if project_id is not None and ProjectRepository(session).get(project_id) is None:
                    raise EntityNotFoundError(f"Project {project_id} was not found")
                self._check_backpressure(repository, project_id=project_id)
                if chapter_id is not None:
                    active = repository.active_for_chapter(chapter_id)
                    if active is not None:
                        raise InvalidStateError(f"Chapter already has active job {active.id}")
                job = repository.add(
                    Job(
                        project_id=project_id,
                        chapter_id=chapter_id,
                        workflow_run_id=workflow_run_id,
                        job_type=job_type,
                        queue_name=self._queue_name(definition.queue_name),
                        status=JobStatus.OUTBOX_PENDING,
                        priority=priority,
                        idempotency_key=idempotency_key,
                        payload=normalized,
                        payload_schema_version=1,
                        max_attempts=min(definition.max_attempts, self._settings.job_max_attempts),
                        correlation_id=correlation_id or str(uuid4()),
                    )
                )
                self._event(
                    session,
                    job,
                    JobEventType.JOB_CREATED,
                    code="job.created",
                    message="Job created",
                )
                self._create_outbox(session, job, reason="create")
                return JobCreationResult(job_id=job.id, reused=False)
        except IntegrityError:
            with self._session_factory() as session:
                existing = JobRepository(session).get_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return JobCreationResult(job_id=existing.id, reused=True)
            raise InvalidStateError("A concurrent active job already exists") from None

    def get(self, job_id: int) -> Job:
        with self._session_factory() as session:
            row = JobRepository(session).get(job_id)
            if row is None:
                raise EntityNotFoundError(f"Job {job_id} was not found")
            session.expunge(row)
            return row

    def request_cancel(self, job_id: int) -> Job:
        with self._session_factory.begin() as session:
            job = self._require_locked(session, job_id)
            previous_status = job.status
            if job.status is JobStatus.CANCEL_REQUESTED:
                return job
            if job.status in {JobStatus.SUCCEEDED, JobStatus.CANCELLED, JobStatus.DEAD_LETTERED}:
                raise InvalidStateError(f"Job in status {job.status} cannot be cancelled")
            transition_job(job, JobStatus.CANCEL_REQUESTED)
            job.cancel_requested_at = utc_now()
            self._event(
                session,
                job,
                JobEventType.CANCEL_REQUESTED,
                code="job.cancel_requested",
                message="Cancellation requested",
            )
            if job.started_at is None or previous_status is JobStatus.PAUSED:
                transition_job(job, JobStatus.CANCELLED)
                self._cancel_linked_workflow(session, job)
                self._event(
                    session,
                    job,
                    JobEventType.JOB_CANCELLED,
                    code="job.cancelled",
                    message="Job cancelled before execution",
                )
            return job

    @staticmethod
    def _cancel_linked_workflow(session: Session, job: Job) -> None:
        if job.workflow_run_id is None:
            return
        run = WorkflowRunRepository(session).get(job.workflow_run_id)
        if run is None or run.status not in {
            WorkflowRunStatus.PENDING,
            WorkflowRunStatus.RUNNING,
            WorkflowRunStatus.PAUSED,
        }:
            return
        now = utc_now()
        transition_workflow(run, WorkflowRunStatus.CANCELLED)
        run.current_node = "cancelled"
        run.finished_at = now
        run.updated_at = now
        chapter = ChapterRepository(session).get(run.chapter_id)
        if chapter is not None:
            chapter.status = (
                ChapterStatus.ACCEPTED
                if chapter.accepted_version_id is not None
                else ChapterStatus.WORKFLOW_FAILED
            )

    def request_pause(self, job_id: int) -> Job:
        with self._session_factory.begin() as session:
            job = self._require_locked(session, job_id)
            if job.status is JobStatus.PAUSED:
                return job
            if job.status not in {
                JobStatus.OUTBOX_PENDING,
                JobStatus.QUEUED,
                JobStatus.LEASED,
                JobStatus.RUNNING,
            }:
                raise InvalidStateError(f"Job in status {job.status} cannot be paused")
            transition_job(job, JobStatus.PAUSE_REQUESTED)
            self._event(
                session,
                job,
                JobEventType.PAUSE_REQUESTED,
                code="job.pause_requested",
                message="Pause requested",
            )
            if job.started_at is None:
                transition_job(job, JobStatus.PAUSED)
                self._event(
                    session,
                    job,
                    JobEventType.JOB_PAUSED,
                    code="job.paused",
                    message="Job paused before execution",
                )
            return job

    def resume(self, job_id: int) -> Job:
        with self._session_factory.begin() as session:
            job = self._require_locked(session, job_id)
            if job.status is not JobStatus.PAUSED:
                raise InvalidStateError("Only paused jobs can be resumed")
            transition_job(job, JobStatus.OUTBOX_PENDING)
            job.finished_at = None
            self._event(
                session,
                job,
                JobEventType.RESUME_REQUESTED,
                code="job.resume_requested",
                message="Job resume requested",
            )
            self._create_outbox(session, job, reason=f"resume-{job.attempt + 1}")
            return job

    def retry_dead_letter(self, job_id: int) -> Job:
        with self._session_factory.begin() as session:
            job = self._require_locked(session, job_id)
            if job.status is not JobStatus.DEAD_LETTERED:
                raise InvalidStateError("Only dead-lettered jobs can be retried explicitly")
            transition_job(job, JobStatus.OUTBOX_PENDING)
            job.max_attempts = job.attempt + self._registry.get(job.job_type).max_attempts
            job.available_at = utc_now()
            job.finished_at = None
            job.error_code = None
            job.error_message = None
            self._event(
                session,
                job,
                JobEventType.RESUME_REQUESTED,
                code="job.dlq_retry_requested",
                message="Dead-letter retry requested",
            )
            self._create_outbox(session, job, reason=f"dlq-retry-{job.attempt + 1}")
            return job

    def discard_dead_letter(self, job_id: int) -> Job:
        with self._session_factory.begin() as session:
            job = self._require_locked(session, job_id)
            if job.status is not JobStatus.DEAD_LETTERED:
                raise InvalidStateError("Only dead-lettered jobs can be discarded")
            job.result = {**job.result, "discarded": True}
            self._event(
                session,
                job,
                JobEventType.JOB_DISCARDED,
                code="job.discarded",
                message="Dead-letter job discarded",
            )
            return job

    def record_event(
        self,
        job_id: int,
        event_type: JobEventType,
        *,
        code: str,
        message: str,
        step: str | None = None,
        progress: int | None = None,
        workflow_event_id: int | None = None,
    ) -> JobEvent:
        with self._session_factory.begin() as session:
            job = self._require_locked(session, job_id)
            if progress is not None:
                job.progress = progress
            if step is not None:
                job.current_step = step
            event = self._event(
                session,
                job,
                event_type,
                code=code,
                message=message,
                workflow_event_id=workflow_event_id,
            )
        self.notify_event(event)
        return event

    def notify_event(self, event: JobEvent) -> None:
        """Publish an optional wake-up after the durable transaction has committed."""
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(event.job_id, event.id)
        except QueueUnavailableError:
            # PostgreSQL is authoritative; a missed wake-up only triggers SSE polling fallback.
            return

    def safe_error(self, error: BaseException) -> tuple[str, str]:
        rendered, _ = self._redaction.redact(str(error))
        return type(error).__name__[:100], rendered[:1000]

    def _check_backpressure(self, repository: JobRepository, *, project_id: int | None) -> None:
        total = repository.active_count()
        if total >= self._settings.queue_pending_soft_limit:
            logger.warning(
                "queue_soft_limit_exceeded pending_jobs=%s soft_limit=%s",
                total,
                self._settings.queue_pending_soft_limit,
            )
        if total >= self._settings.queue_pending_hard_limit:
            raise QueueBackpressureError("Global queue hard limit reached")
        if project_id is not None:
            project_total = repository.active_count(project_id=project_id)
            if project_total >= self._settings.project_pending_limit:
                raise QueueBackpressureError("Project queue limit reached")

    def _create_outbox(self, session: Any, job: Job, *, reason: str) -> OutboxMessage:
        deduplication_key = f"job:{job.id}:{reason}"
        existing = OutboxRepository(session).get_by_deduplication_key(deduplication_key)
        if existing is not None:
            return existing
        return OutboxRepository(session).add(
            OutboxMessage(
                aggregate_type="job",
                aggregate_id=job.id,
                event_type="job.enqueue",
                payload={"job_id": job.id, "queue_name": job.queue_name},
                status=OutboxStatus.PENDING,
                deduplication_key=deduplication_key,
            )
        )

    @staticmethod
    def _event(
        session: Any,
        job: Job,
        event_type: JobEventType,
        *,
        code: str,
        message: str,
        workflow_event_id: int | None = None,
    ) -> JobEvent:
        return JobEventRepository(session).add_ordered(
            JobEvent(
                job_id=job.id,
                sequence=0,
                event_type=event_type,
                status=job.status,
                step=job.current_step,
                progress=job.progress,
                message_code=code,
                message=message[:500],
                attempt=job.attempt,
                worker_id=job.worker_id,
                workflow_event_id=workflow_event_id,
            )
        )

    @staticmethod
    def _require_locked(session: Any, job_id: int) -> Job:
        job = JobRepository(session).get_for_update(job_id)
        if job is None:
            raise EntityNotFoundError(f"Job {job_id} was not found")
        return job

    def _queue_name(self, name: str) -> str:
        return f"{self._settings.queue_prefix}.{name.rsplit('.', 1)[-1]}"

    @staticmethod
    def _validate_payload(payload: dict[str, object]) -> None:
        def inspect(value: object, path: tuple[str, ...] = ()) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    normalized = str(key).casefold()
                    if normalized in _SENSITIVE_KEYS or normalized.endswith("_key"):
                        raise DomainValidationError(
                            f"Job payload cannot contain sensitive field {'.'.join((*path, str(key)))}"
                        )
                    inspect(item, (*path, str(key)))
            elif isinstance(value, list):
                for item in value:
                    inspect(item, path)
            elif not isinstance(value, (str, int, float, bool, type(None))):
                raise DomainValidationError("Job payload must be JSON-compatible")

        inspect(payload)

    @staticmethod
    def _idempotency_key(
        *,
        job_type: JobType,
        project_id: int | None,
        chapter_id: int | None,
        workflow_run_id: int | None,
        operation: str,
        payload: dict[str, object],
        external_key: str | None,
    ) -> str:
        body = {
            "job_type": job_type.value,
            "project_id": project_id,
            "chapter_id": chapter_id,
            "workflow_run_id": workflow_run_id,
            "operation": operation,
            "payload_schema_version": 1,
            "payload": payload,
            "external_key": external_key or "",
        }
        return hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def retry_available_at(attempt: int, *, now: datetime | None = None) -> datetime:
    """Bounded non-blocking exponential retry schedule."""
    timestamp = now or datetime.now(UTC)
    delay_seconds = min(300, 2 ** max(0, attempt - 1))
    return timestamp + timedelta(seconds=delay_seconds)
