"""Central asynchronous job state machine."""

from __future__ import annotations

from datetime import datetime

from storyforge.enums import JobStatus
from storyforge.exceptions import InvalidStateError
from storyforge.models import Job
from storyforge.models.base import utc_now

TERMINAL_JOB_STATUSES = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.DEAD_LETTERED}
)

_ALLOWED: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.PENDING: frozenset({JobStatus.OUTBOX_PENDING, JobStatus.CANCEL_REQUESTED}),
    JobStatus.OUTBOX_PENDING: frozenset(
        {
            JobStatus.QUEUED,
            JobStatus.PAUSE_REQUESTED,
            JobStatus.CANCEL_REQUESTED,
            JobStatus.FAILED,
        }
    ),
    JobStatus.QUEUED: frozenset(
        {
            JobStatus.LEASED,
            JobStatus.PAUSE_REQUESTED,
            JobStatus.CANCEL_REQUESTED,
            JobStatus.RETRY_SCHEDULED,
        }
    ),
    JobStatus.LEASED: frozenset(
        {
            JobStatus.RUNNING,
            JobStatus.QUEUED,
            JobStatus.RETRY_SCHEDULED,
            JobStatus.CANCEL_REQUESTED,
        }
    ),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.RETRY_SCHEDULED,
            JobStatus.PAUSE_REQUESTED,
            JobStatus.CANCEL_REQUESTED,
        }
    ),
    JobStatus.PAUSE_REQUESTED: frozenset(
        {JobStatus.PAUSED, JobStatus.CANCEL_REQUESTED, JobStatus.FAILED}
    ),
    JobStatus.PAUSED: frozenset({JobStatus.OUTBOX_PENDING, JobStatus.CANCEL_REQUESTED}),
    JobStatus.CANCEL_REQUESTED: frozenset({JobStatus.CANCELLED, JobStatus.FAILED}),
    JobStatus.CANCELLED: frozenset(),
    JobStatus.RETRY_SCHEDULED: frozenset(
        {
            JobStatus.OUTBOX_PENDING,
            JobStatus.QUEUED,
            JobStatus.CANCEL_REQUESTED,
            JobStatus.DEAD_LETTERED,
        }
    ),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset({JobStatus.RETRY_SCHEDULED, JobStatus.DEAD_LETTERED}),
    JobStatus.DEAD_LETTERED: frozenset({JobStatus.OUTBOX_PENDING}),
}


def transition_job(job: Job, target: JobStatus, *, now: datetime | None = None) -> None:
    """Apply one legal state transition and common terminal timestamps."""
    if target is job.status:
        return
    if target not in _ALLOWED[job.status]:
        raise InvalidStateError(f"Job cannot transition from {job.status} to {target}")
    timestamp = now or utc_now()
    job.status = target
    job.updated_at = timestamp
    if target in TERMINAL_JOB_STATUSES or target is JobStatus.FAILED:
        job.finished_at = timestamp
        job.lease_expires_at = None
        job.heartbeat_at = None
        job.worker_id = None
    if target is JobStatus.CANCELLED:
        job.cancelled_at = timestamp


def is_terminal_job(status: JobStatus) -> bool:
    return status in TERMINAL_JOB_STATUSES
