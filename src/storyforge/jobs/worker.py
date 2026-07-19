"""Database-leased Job executor used by Dramatiq workers and inline tests."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from storyforge import __version__
from storyforge.database import SessionFactory
from storyforge.enums import (
    JobEventType,
    JobStatus,
    OutboxStatus,
    WorkerStatus,
    WorkflowRunStatus,
)
from storyforge.exceptions import (
    JobCancellationRequested,
    JobPauseRequested,
    JobRetryableError,
    QueueUnavailableError,
)
from storyforge.jobs.handlers import JobExecutionContext, JobHandlers
from storyforge.jobs.transitions import transition_job
from storyforge.models import Job, JobEvent, OutboxMessage
from storyforge.models.base import utc_now
from storyforge.repositories import (
    JobEventRepository,
    JobRepository,
    OutboxRepository,
    WorkerRepository,
    WorkflowRunRepository,
)
from storyforge.services.jobs import JobService, retry_available_at
from storyforge.settings import Settings
from storyforge.workflows.transitions import transition_workflow


class JobExecutor:
    """Claim one lease, execute once, and persist a bounded outcome."""

    def __init__(
        self,
        session_factory: SessionFactory,
        handlers: JobHandlers,
        settings: Settings,
        *,
        clock: Callable[[], datetime] = utc_now,
        heartbeat_thread: bool = True,
    ) -> None:
        self._session_factory = session_factory
        self._handlers = handlers
        self._settings = settings
        self._clock = clock
        self._heartbeat_thread = heartbeat_thread
        self._jobs = JobService(session_factory, settings)

    def execute(self, job_id: int, *, worker_id: str) -> bool:
        job = self._claim(job_id, worker_id)
        if job is None:
            return False
        stop = threading.Event()
        heartbeat: threading.Thread | None = None
        if self._heartbeat_thread:
            heartbeat = threading.Thread(
                target=self._heartbeat_loop,
                args=(job_id, worker_id, stop),
                daemon=True,
            )
            heartbeat.start()
        try:
            context = JobExecutionContext(self._session_factory, self._jobs, job.id)
            result = self._handlers.handle(job, context)
            self._succeed(job.id, worker_id, result.model_dump(mode="json"))
        except JobCancellationRequested:
            self._cancel(job.id, worker_id)
        except JobPauseRequested:
            self._pause(job.id, worker_id)
        except (JobRetryableError, OperationalError, QueueUnavailableError) as exc:
            self._retry_or_dead_letter(job.id, worker_id, exc)
        except Exception as exc:
            self._fail(job.id, worker_id, exc)
        finally:
            stop.set()
            if heartbeat is not None:
                heartbeat.join(timeout=max(1.0, self._settings.worker_heartbeat_seconds * 2))
            self._worker_heartbeat(worker_id, WorkerStatus.IDLE, None)
        return True

    def heartbeat(self, job_id: int, worker_id: str) -> bool:
        now = self._clock()
        with self._session_factory.begin() as session:
            job = JobRepository(session).get_for_update(job_id)
            if (
                job is None
                or job.worker_id != worker_id
                or job.status not in {JobStatus.LEASED, JobStatus.RUNNING}
            ):
                return False
            job.heartbeat_at = now
            job.lease_expires_at = now + timedelta(seconds=self._settings.job_lease_seconds)
            job.updated_at = now
        self._worker_heartbeat(worker_id, WorkerStatus.BUSY, job_id)
        return True

    def recover_expired(self) -> int:
        now = self._clock()
        recovered = 0
        with self._session_factory.begin() as session:
            repository = JobRepository(session)
            for job in repository.expired_leases(now):
                if job.workflow_run_id is not None:
                    workflow = WorkflowRunRepository(session).get(job.workflow_run_id)
                    if workflow is not None and workflow.status is WorkflowRunStatus.RUNNING:
                        transition_workflow(workflow, WorkflowRunStatus.PAUSED)
                        workflow.updated_at = now
                if job.attempt >= job.max_attempts:
                    transition_job(job, JobStatus.FAILED, now=now)
                    transition_job(job, JobStatus.DEAD_LETTERED, now=now)
                    self._event(
                        session,
                        job,
                        JobEventType.JOB_DEAD_LETTERED,
                        "job.lease_exhausted",
                        "Expired lease exhausted attempts",
                    )
                else:
                    transition_job(job, JobStatus.RETRY_SCHEDULED, now=now)
                    job.worker_id = None
                    job.lease_expires_at = None
                    job.heartbeat_at = None
                    job.available_at = retry_available_at(job.attempt, now=now)
                    self._retry_outbox(session, job)
                    self._event(
                        session,
                        job,
                        JobEventType.RETRY_SCHEDULED,
                        "job.lease_recovered",
                        "Expired worker lease scheduled for recovery",
                    )
                recovered += 1
        return recovered

    def _claim(self, job_id: int, worker_id: str) -> Job | None:
        now = self._clock()
        with self._session_factory.begin() as session:
            job = JobRepository(session).claim(
                job_id,
                worker_id=worker_id,
                now=now,
                lease_expires_at=now + timedelta(seconds=self._settings.job_lease_seconds),
            )
            if job is None:
                return None
            self._event(
                session,
                job,
                JobEventType.JOB_LEASED,
                "job.leased",
                "Job leased by worker",
            )
            transition_job(job, JobStatus.RUNNING, now=now)
            if job.started_at is None:
                job.started_at = now
            self._event(
                session,
                job,
                JobEventType.JOB_STARTED,
                "job.started",
                "Job execution started",
            )
            session.flush()
            session.expunge(job)
        self._worker_heartbeat(worker_id, WorkerStatus.BUSY, job_id)
        return job

    def _succeed(self, job_id: int, worker_id: str, result: dict[str, object]) -> None:
        with self._session_factory.begin() as session:
            job = self._owned_job(session, job_id, worker_id)
            if job.status is JobStatus.CANCEL_REQUESTED:
                transition_job(job, JobStatus.CANCELLED, now=self._clock())
                event_type = JobEventType.JOB_CANCELLED
                code = "job.cancelled"
                message = "Job cancelled at a safe boundary"
            elif job.status is JobStatus.PAUSE_REQUESTED:
                transition_job(job, JobStatus.PAUSED, now=self._clock())
                event_type = JobEventType.JOB_PAUSED
                code = "job.paused"
                message = "Job paused at a safe boundary"
            else:
                transition_job(job, JobStatus.SUCCEEDED, now=self._clock())
                job.result = result
                job.progress = 100
                job.current_step = "completed"
                event_type = JobEventType.JOB_SUCCEEDED
                code = "job.succeeded"
                message = "Job succeeded"
            self._event(session, job, event_type, code, message)

    def _cancel(self, job_id: int, worker_id: str) -> None:
        with self._session_factory.begin() as session:
            job = self._owned_job(session, job_id, worker_id)
            if job.status is not JobStatus.CANCEL_REQUESTED:
                transition_job(job, JobStatus.CANCEL_REQUESTED, now=self._clock())
            transition_job(job, JobStatus.CANCELLED, now=self._clock())
            self._event(
                session,
                job,
                JobEventType.JOB_CANCELLED,
                "job.cancelled",
                "Job cancelled at a safe boundary",
            )

    def _pause(self, job_id: int, worker_id: str) -> None:
        with self._session_factory.begin() as session:
            job = self._owned_job(session, job_id, worker_id)
            if job.status is not JobStatus.PAUSE_REQUESTED:
                transition_job(job, JobStatus.PAUSE_REQUESTED, now=self._clock())
            transition_job(job, JobStatus.PAUSED, now=self._clock())
            job.lease_expires_at = None
            job.worker_id = None
            self._event(
                session,
                job,
                JobEventType.JOB_PAUSED,
                "job.paused",
                "Job paused at a safe boundary",
            )

    def _retry_or_dead_letter(self, job_id: int, worker_id: str, error: BaseException) -> None:
        code, message = self._jobs.safe_error(error)
        with self._session_factory.begin() as session:
            job = self._owned_job(session, job_id, worker_id)
            job.error_code = code
            job.error_message = message
            if job.attempt >= job.max_attempts:
                transition_job(job, JobStatus.FAILED, now=self._clock())
                transition_job(job, JobStatus.DEAD_LETTERED, now=self._clock())
                self._event(
                    session,
                    job,
                    JobEventType.JOB_DEAD_LETTERED,
                    "job.dead_lettered",
                    "Job exhausted infrastructure retries",
                )
                return
            transition_job(job, JobStatus.RETRY_SCHEDULED, now=self._clock())
            job.worker_id = None
            job.lease_expires_at = None
            job.heartbeat_at = None
            job.available_at = retry_available_at(job.attempt, now=self._clock())
            self._retry_outbox(session, job)
            self._event(
                session,
                job,
                JobEventType.RETRY_SCHEDULED,
                "job.retry_scheduled",
                "Infrastructure retry scheduled",
            )

    def _fail(self, job_id: int, worker_id: str, error: BaseException) -> None:
        code, message = self._jobs.safe_error(error)
        with self._session_factory.begin() as session:
            job = self._owned_job(session, job_id, worker_id)
            transition_job(job, JobStatus.FAILED, now=self._clock())
            job.error_code = code
            job.error_message = message
            self._event(
                session,
                job,
                JobEventType.JOB_FAILED,
                "job.failed",
                "Job failed without automatic retry",
            )

    def _heartbeat_loop(self, job_id: int, worker_id: str, stop: threading.Event) -> None:
        while not stop.wait(self._settings.worker_heartbeat_seconds):
            try:
                active = self.heartbeat(job_id, worker_id)
            except SQLAlchemyError:
                return
            if not active:
                return

    def _worker_heartbeat(
        self, worker_id: str, status: WorkerStatus, current_job_id: int | None
    ) -> None:
        try:
            with self._session_factory.begin() as session:
                WorkerRepository(session).heartbeat(
                    worker_id=worker_id,
                    queue_name="all",
                    status=status,
                    current_job_id=current_job_id,
                    version=__version__,
                    now=self._clock(),
                )
        except SQLAlchemyError:
            return

    @staticmethod
    def _owned_job(session: Session, job_id: int, worker_id: str) -> Job:
        job = JobRepository(session).get_for_update(job_id)
        if job is None or job.worker_id != worker_id:
            raise RuntimeError("Worker no longer owns the job lease")
        return job

    @staticmethod
    def _event(
        session: Session,
        job: Job,
        event_type: JobEventType,
        code: str,
        message: str,
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
                message=message,
                attempt=job.attempt,
                worker_id=job.worker_id,
            )
        )

    @staticmethod
    def _retry_outbox(session: Session, job: Job) -> OutboxMessage:
        return OutboxRepository(session).add(
            OutboxMessage(
                aggregate_type="job",
                aggregate_id=job.id,
                event_type="job.enqueue",
                payload={"job_id": job.id, "queue_name": job.queue_name},
                status=OutboxStatus.PENDING,
                available_at=job.available_at,
                deduplication_key=f"job:{job.id}:attempt:{job.attempt + 1}",
            )
        )
