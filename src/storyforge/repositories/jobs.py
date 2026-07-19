"""Persistence access for jobs, outbox delivery, events, and workers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from storyforge.enums import JobStatus, JobType, OutboxStatus, WorkerStatus
from storyforge.models import Chapter, Job, JobEvent, OutboxMessage, WorkerRecord
from storyforge.repositories.base import PageSlice, Repository

ACTIVE_JOB_STATUSES = (
    JobStatus.PENDING,
    JobStatus.OUTBOX_PENDING,
    JobStatus.QUEUED,
    JobStatus.LEASED,
    JobStatus.RUNNING,
    JobStatus.PAUSE_REQUESTED,
    JobStatus.PAUSED,
    JobStatus.CANCEL_REQUESTED,
    JobStatus.RETRY_SCHEDULED,
)


class JobRepository(Repository[Job]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Job)

    def get_by_idempotency_key(self, key: str) -> Job | None:
        return self.session.scalar(select(Job).where(Job.idempotency_key == key))

    def get_for_update(self, job_id: int) -> Job | None:
        return self.session.scalar(select(Job).where(Job.id == job_id).with_for_update())

    def active_count(self, *, project_id: int | None = None) -> int:
        statement = select(func.count(Job.id)).where(Job.status.in_(ACTIVE_JOB_STATUSES))
        if project_id is not None:
            statement = statement.where(Job.project_id == project_id)
        return int(self.session.scalar(statement) or 0)

    def active_for_chapter(self, chapter_id: int) -> Job | None:
        return self.session.scalar(
            select(Job)
            .where(Job.chapter_id == chapter_id, Job.status.in_(ACTIVE_JOB_STATUSES))
            .order_by(Job.id.desc())
            .limit(1)
        )

    def page_filtered(
        self,
        *,
        page: int,
        page_size: int,
        status: JobStatus | None = None,
        job_type: JobType | None = None,
        project_id: int | None = None,
        chapter_id: int | None = None,
        chapter_number: int | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> PageSlice[Job]:
        statement = select(Job)
        if status is not None:
            statement = statement.where(Job.status == status)
        if job_type is not None:
            statement = statement.where(Job.job_type == job_type)
        if project_id is not None:
            statement = statement.where(Job.project_id == project_id)
        if chapter_id is not None:
            statement = statement.where(Job.chapter_id == chapter_id)
        if chapter_number is not None:
            statement = statement.join(Chapter, Chapter.id == Job.chapter_id).where(
                Chapter.chapter_number == chapter_number
            )
        if created_from is not None:
            statement = statement.where(Job.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(Job.created_at <= created_to)
        return self.paginate(statement.order_by(Job.id.desc()), page=page, page_size=page_size)

    def claim(
        self,
        job_id: int,
        *,
        worker_id: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> Job | None:
        result = cast(
            CursorResult[Any],
            self.session.execute(
                update(Job)
                .where(
                    Job.id == job_id,
                    Job.status.in_(
                        (JobStatus.OUTBOX_PENDING, JobStatus.QUEUED, JobStatus.RETRY_SCHEDULED)
                    ),
                    Job.available_at <= now,
                )
                .values(
                    status=JobStatus.LEASED,
                    worker_id=worker_id,
                    heartbeat_at=now,
                    lease_expires_at=lease_expires_at,
                    attempt=Job.attempt + 1,
                    updated_at=now,
                )
            ),
        )
        if result.rowcount != 1:
            return None
        self.session.flush()
        return self.get(job_id)

    def expired_leases(self, now: datetime, *, limit: int = 100) -> list[Job]:
        statement = (
            select(Job)
            .where(
                Job.status.in_((JobStatus.LEASED, JobStatus.RUNNING)),
                Job.lease_expires_at.is_not(None),
                Job.lease_expires_at <= now,
            )
            .order_by(Job.lease_expires_at, Job.id)
            .limit(limit)
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        else:
            statement = statement.with_for_update()
        return list(self.session.scalars(statement))

    def stale_queued(self, cutoff: datetime, *, limit: int = 100) -> list[Job]:
        statement = (
            select(Job)
            .where(
                Job.status == JobStatus.QUEUED,
                Job.queued_at.is_not(None),
                Job.queued_at <= cutoff,
            )
            .order_by(Job.queued_at, Job.id)
            .limit(limit)
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        else:
            statement = statement.with_for_update()
        return list(self.session.scalars(statement))


class JobEventRepository(Repository[JobEvent]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, JobEvent)

    def add_ordered(self, event: JobEvent) -> JobEvent:
        sequence = self.session.scalar(
            update(Job)
            .where(Job.id == event.job_id)
            .values(event_sequence=Job.event_sequence + 1)
            .returning(Job.event_sequence)
        )
        if sequence is None:
            raise ValueError(f"Job {event.job_id} was not found for event allocation")
        event.sequence = int(sequence)
        return self.add(event)

    def list_after(
        self, job_id: int, *, after_id: int | None = None, limit: int = 500
    ) -> list[JobEvent]:
        statement = select(JobEvent).where(JobEvent.job_id == job_id)
        if after_id is not None:
            statement = statement.where(JobEvent.id > after_id)
        return list(self.session.scalars(statement.order_by(JobEvent.id).limit(limit)))

    def page_for_job(self, job_id: int, *, page: int, page_size: int) -> PageSlice[JobEvent]:
        return self.paginate(
            select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.id),
            page=page,
            page_size=page_size,
        )


class OutboxRepository(Repository[OutboxMessage]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, OutboxMessage)

    def claim_batch(
        self,
        *,
        dispatcher_id: str,
        now: datetime,
        limit: int,
        stale_before: datetime | None = None,
    ) -> list[OutboxMessage]:
        claimable = OutboxMessage.status == OutboxStatus.PENDING
        if stale_before is not None:
            claimable = or_(
                claimable,
                and_(
                    OutboxMessage.status == OutboxStatus.CLAIMED,
                    OutboxMessage.claimed_at <= stale_before,
                ),
            )
        statement = (
            select(OutboxMessage)
            .join(Job, Job.id == OutboxMessage.aggregate_id)
            .where(
                claimable,
                OutboxMessage.available_at <= now,
            )
            .order_by(Job.priority.desc(), OutboxMessage.id)
            .limit(limit)
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        else:
            statement = statement.with_for_update()
        rows = list(self.session.scalars(statement))
        for row in rows:
            row.status = OutboxStatus.CLAIMED
            row.claimed_by = dispatcher_id
            row.claimed_at = now
            row.attempt += 1
        self.session.flush()
        return rows

    def get_by_deduplication_key(self, key: str) -> OutboxMessage | None:
        return self.session.scalar(
            select(OutboxMessage).where(OutboxMessage.deduplication_key == key)
        )

    def latest_for_job(self, job_id: int) -> OutboxMessage | None:
        return self.session.scalar(
            select(OutboxMessage)
            .where(
                OutboxMessage.aggregate_type == "job",
                OutboxMessage.aggregate_id == job_id,
            )
            .order_by(OutboxMessage.id.desc())
            .limit(1)
            .with_for_update()
        )


class WorkerRepository(Repository[WorkerRecord]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, WorkerRecord)

    def get_by_worker_id(self, worker_id: str) -> WorkerRecord | None:
        return self.session.scalar(select(WorkerRecord).where(WorkerRecord.worker_id == worker_id))

    def list_recent(self, *, limit: int = 100) -> list[WorkerRecord]:
        return list(
            self.session.scalars(
                select(WorkerRecord).order_by(WorkerRecord.last_heartbeat_at.desc()).limit(limit)
            )
        )

    def heartbeat(
        self,
        *,
        worker_id: str,
        queue_name: str,
        status: WorkerStatus,
        current_job_id: int | None,
        version: str,
        now: datetime,
    ) -> WorkerRecord:
        dialect = self.session.bind.dialect.name if self.session.bind is not None else ""
        values = {
            "worker_id": worker_id,
            "queue_name": queue_name,
            "status": status,
            "current_job_id": current_job_id,
            "version": version,
            "started_at": now,
            "last_heartbeat_at": now,
        }
        updates = {
            "queue_name": queue_name,
            "status": status,
            "current_job_id": current_job_id,
            "version": version,
            "last_heartbeat_at": now,
        }
        if dialect == "postgresql":
            postgresql_statement = postgresql_insert(WorkerRecord).values(**values)
            self.session.execute(
                postgresql_statement.on_conflict_do_update(
                    index_elements=[WorkerRecord.worker_id], set_=updates
                )
            )
            self.session.flush()
            row = self.get_by_worker_id(worker_id)
            assert row is not None
            return row
        if dialect == "sqlite":
            sqlite_statement = sqlite_insert(WorkerRecord).values(**values)
            self.session.execute(
                sqlite_statement.on_conflict_do_update(
                    index_elements=[WorkerRecord.worker_id], set_=updates
                )
            )
            self.session.flush()
            row = self.get_by_worker_id(worker_id)
            assert row is not None
            return row
        row = self.get_by_worker_id(worker_id)
        if row is None:
            return self.add(
                WorkerRecord(
                    worker_id=worker_id,
                    queue_name=queue_name,
                    status=status,
                    current_job_id=current_job_id,
                    version=version,
                    started_at=now,
                    last_heartbeat_at=now,
                )
            )
        row.queue_name = queue_name
        row.status = status
        row.current_job_id = current_job_id
        row.last_heartbeat_at = now
        row.version = version
        self.session.flush()
        return row

    def keepalive(
        self,
        *,
        worker_id: str,
        queue_name: str,
        version: str,
        now: datetime,
    ) -> WorkerRecord:
        """Register an idle worker or refresh it without overwriting an active Job status."""
        row = self.get_by_worker_id(worker_id)
        if row is None:
            return self.heartbeat(
                worker_id=worker_id,
                queue_name=queue_name,
                status=WorkerStatus.IDLE,
                current_job_id=None,
                version=version,
                now=now,
            )
        row.queue_name = queue_name
        row.version = version
        row.last_heartbeat_at = now
        self.session.flush()
        return row
