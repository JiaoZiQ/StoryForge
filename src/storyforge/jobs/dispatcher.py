"""Transactional-outbox dispatcher with bounded retries."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from storyforge.database import SessionFactory
from storyforge.enums import JobEventType, JobStatus, OutboxStatus
from storyforge.jobs.broker import JobBroker
from storyforge.jobs.registry import JobRegistry
from storyforge.jobs.transitions import transition_job
from storyforge.models import JobEvent
from storyforge.models.base import utc_now
from storyforge.repositories import JobEventRepository, JobRepository, OutboxRepository
from storyforge.services.jobs import JobService, retry_available_at
from storyforge.settings import Settings


class OutboxDispatcher:
    """Claim rows competitively and publish only a Job identifier."""

    def __init__(
        self,
        session_factory: SessionFactory,
        broker: JobBroker,
        settings: Settings,
        *,
        dispatcher_id: str,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._broker = broker
        self._settings = settings
        self._dispatcher_id = dispatcher_id
        self._clock = clock
        self._jobs = JobService(session_factory, settings)
        self._registry = JobRegistry()

    def dispatch_once(self) -> int:
        """Publish one bounded batch and return the successful count."""
        now = self._clock()
        with self._session_factory.begin() as session:
            rows = OutboxRepository(session).claim_batch(
                dispatcher_id=self._dispatcher_id,
                now=now,
                limit=self._settings.outbox_batch_size,
                stale_before=stale_claim_cutoff(now, self._settings.job_lease_seconds),
            )
            row_ids = [row.id for row in rows]
        published = 0
        for row_id in row_ids:
            with self._session_factory() as read_session:
                row = OutboxRepository(read_session).get(row_id)
                if row is None:
                    continue
                job_id = row.aggregate_id
                queue_name = str(row.payload.get("queue_name", ""))
                job = JobRepository(read_session).get(job_id)
                if job is None:
                    continue
                timeout_seconds = self._registry.get(job.job_type).timeout_seconds
            try:
                self._broker.enqueue(job_id, queue_name, timeout_seconds=timeout_seconds)
            except Exception as exc:
                self._record_failure(row_id, exc)
                continue
            self._record_published(row_id)
            published += 1
        return published

    def recover_stranded(self) -> int:
        """Re-open durable enqueue intent after Redis loses an unclaimed message."""
        now = self._clock()
        cutoff = stale_claim_cutoff(now, self._settings.job_lease_seconds)
        recovered = 0
        with self._session_factory.begin() as session:
            jobs = JobRepository(session).stale_queued(
                cutoff, limit=self._settings.outbox_batch_size
            )
            outboxes = OutboxRepository(session)
            for job in jobs:
                outbox = outboxes.latest_for_job(job.id)
                if outbox is None or outbox.status is not OutboxStatus.PUBLISHED:
                    continue
                transition_job(job, JobStatus.RETRY_SCHEDULED, now=now)
                job.available_at = now
                outbox.status = OutboxStatus.PENDING
                outbox.available_at = now
                outbox.claimed_at = None
                outbox.claimed_by = None
                outbox.published_at = None
                JobEventRepository(session).add_ordered(
                    JobEvent(
                        job_id=job.id,
                        sequence=0,
                        event_type=JobEventType.RETRY_SCHEDULED,
                        status=job.status,
                        step=job.current_step,
                        progress=job.progress,
                        message_code="job.redis_recovery_scheduled",
                        message="Queue delivery recovery scheduled",
                        attempt=job.attempt,
                        worker_id=None,
                    )
                )
                recovered += 1
        return recovered

    def _record_published(self, row_id: int) -> None:
        with self._session_factory.begin() as session:
            outbox = OutboxRepository(session).get(row_id)
            if outbox is None or outbox.status is OutboxStatus.PUBLISHED:
                return
            outbox.status = OutboxStatus.PUBLISHED
            outbox.published_at = self._clock()
            outbox.last_error = None
            job = JobRepository(session).get_for_update(outbox.aggregate_id)
            if job is None:
                return
            if job.status in {JobStatus.OUTBOX_PENDING, JobStatus.RETRY_SCHEDULED}:
                job.status = JobStatus.QUEUED
                job.queued_at = self._clock()
                job.updated_at = self._clock()
                JobEventRepository(session).add_ordered(
                    JobEvent(
                        job_id=job.id,
                        sequence=0,
                        event_type=JobEventType.JOB_QUEUED,
                        status=job.status,
                        step=job.current_step,
                        progress=job.progress,
                        message_code="job.queued",
                        message="Job queued",
                        attempt=job.attempt,
                        worker_id=None,
                    )
                )

    def _record_failure(self, row_id: int, error: BaseException) -> None:
        code, message = self._jobs.safe_error(error)
        with self._session_factory.begin() as session:
            outbox = OutboxRepository(session).get(row_id)
            if outbox is None:
                return
            outbox.last_error = f"{code}: {message}"[:1000]
            outbox.claimed_at = None
            outbox.claimed_by = None
            if outbox.attempt >= self._settings.job_max_attempts:
                outbox.status = OutboxStatus.FAILED
                job = JobRepository(session).get_for_update(outbox.aggregate_id)
                if job is not None and job.status in {
                    JobStatus.OUTBOX_PENDING,
                    JobStatus.RETRY_SCHEDULED,
                }:
                    if job.status is JobStatus.OUTBOX_PENDING:
                        transition_job(job, JobStatus.FAILED, now=self._clock())
                    transition_job(job, JobStatus.DEAD_LETTERED, now=self._clock())
                    job.error_code = "outbox_publish_failed"
                    job.error_message = "Job could not be published to the queue"
                    JobEventRepository(session).add_ordered(
                        JobEvent(
                            job_id=job.id,
                            sequence=0,
                            event_type=JobEventType.JOB_DEAD_LETTERED,
                            status=job.status,
                            step=job.current_step,
                            progress=job.progress,
                            message_code="job.outbox_dead_lettered",
                            message="Queue publishing exhausted attempts",
                            attempt=job.attempt,
                            worker_id=None,
                        )
                    )
            else:
                outbox.status = OutboxStatus.PENDING
                outbox.available_at = retry_available_at(outbox.attempt, now=self._clock())


def stale_claim_cutoff(now: datetime, lease_seconds: float) -> datetime:
    return now - timedelta(seconds=lease_seconds)
