"""Application boundary for asynchronous admission, controls, and safe projections."""

from datetime import UTC, datetime, timedelta

from storyforge.database import SessionFactory
from storyforge.enums import JobStatus, JobType, WorkerStatus
from storyforge.exceptions import EntityNotFoundError
from storyforge.models import Job, JobEvent, WorkerRecord
from storyforge.models.base import utc_now
from storyforge.repositories import (
    ChapterRepository,
    JobEventRepository,
    JobRepository,
    WorkerRepository,
)
from storyforge.schemas.jobs import (
    JobAcceptedResponse,
    JobCreateRequest,
    JobEventPageResponse,
    JobEventResponse,
    JobPageResponse,
    JobResponse,
    QueueHealthResponse,
    WorkerResponse,
)
from storyforge.services.jobs import JobService
from storyforge.settings import Settings


class JobApplicationService:
    """Keep HTTP and CLI adapters free of persistence and state-machine logic."""

    def __init__(self, session_factory: SessionFactory, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._jobs = JobService(session_factory, settings)

    def create(self, request: JobCreateRequest) -> JobAcceptedResponse:
        chapter_id: int | None = None
        payload = dict(request.payload)
        if request.chapter_number is not None:
            if request.project_id is None:
                raise EntityNotFoundError("project_id is required with chapter_number")
            with self._session_factory() as session:
                chapter = ChapterRepository(session).get_by_number(
                    request.project_id, request.chapter_number
                )
                if chapter is None:
                    raise EntityNotFoundError("Chapter was not found")
                chapter_id = chapter.id
            payload.setdefault("chapter_number", request.chapter_number)
        result = self._jobs.create(
            job_type=request.job_type,
            project_id=request.project_id,
            chapter_id=chapter_id,
            workflow_run_id=request.workflow_run_id,
            payload=payload,
            operation=request.operation,
            external_idempotency_key=request.idempotency_key,
            priority=request.priority,
        )
        job = self._jobs.get(result.job_id)
        return JobAcceptedResponse(
            job_id=job.id,
            status=job.status,
            reused=result.reused,
            status_url=f"/api/v1/jobs/{job.id}",
            events_url=f"/api/v1/jobs/{job.id}/events",
        )

    def get(self, job_id: int) -> JobResponse:
        return _job_response(self._jobs.get(job_id))

    def list_jobs(
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
    ) -> JobPageResponse:
        with self._session_factory() as session:
            result = JobRepository(session).page_filtered(
                page=page,
                page_size=page_size,
                status=status,
                job_type=job_type,
                project_id=project_id,
                chapter_id=chapter_id,
                chapter_number=chapter_number,
                created_from=created_from,
                created_to=created_to,
            )
            return JobPageResponse(
                items=[_job_response(item) for item in result.items],
                page=page,
                page_size=page_size,
                total_items=result.total_items,
            )

    def events(self, job_id: int, *, page: int, page_size: int) -> JobEventPageResponse:
        self._jobs.get(job_id)
        with self._session_factory() as session:
            result = JobEventRepository(session).page_for_job(
                job_id, page=page, page_size=page_size
            )
            return JobEventPageResponse(
                items=[_event_response(item) for item in result.items],
                page=page,
                page_size=page_size,
                total_items=result.total_items,
            )

    def events_after(self, job_id: int, after_id: int | None) -> list[JobEventResponse]:
        self._jobs.get(job_id)
        with self._session_factory() as session:
            return [
                _event_response(item)
                for item in JobEventRepository(session).list_after(job_id, after_id=after_id)
            ]

    def cancel(self, job_id: int) -> JobResponse:
        self._jobs.request_cancel(job_id)
        return self.get(job_id)

    def pause(self, job_id: int) -> JobResponse:
        self._jobs.request_pause(job_id)
        return self.get(job_id)

    def resume(self, job_id: int) -> JobResponse:
        self._jobs.resume(job_id)
        return self.get(job_id)

    def retry(self, job_id: int) -> JobResponse:
        self._jobs.retry_dead_letter(job_id)
        return self.get(job_id)

    def discard(self, job_id: int) -> JobResponse:
        self._jobs.discard_dead_letter(job_id)
        return self.get(job_id)

    def health(self, broker_reachable: bool) -> QueueHealthResponse:
        now = utc_now()
        with self._session_factory() as session:
            pending = JobRepository(session).active_count()
            workers = WorkerRepository(session).list_recent()
        return QueueHealthResponse(
            mode=self._settings.job_execution_mode,
            broker_reachable=broker_reachable,
            pending_jobs=pending,
            soft_limit_exceeded=pending >= self._settings.queue_pending_soft_limit,
            pending_soft_limit=self._settings.queue_pending_soft_limit,
            pending_hard_limit=self._settings.queue_pending_hard_limit,
            project_pending_limit=self._settings.project_pending_limit,
            workers=[
                _worker_response(
                    item,
                    now=now,
                    offline_after_seconds=self._settings.worker_offline_after_seconds,
                )
                for item in workers
            ],
        )


def _job_response(job: Job) -> JobResponse:
    chapter_number = job.payload.get("chapter_number")
    return JobResponse.model_validate(
        {
            **{
                name: getattr(job, name)
                for name in JobResponse.model_fields
                if name != "chapter_number"
            },
            "chapter_number": chapter_number if isinstance(chapter_number, int) else None,
        }
    )


def _event_response(event: JobEvent) -> JobEventResponse:
    return JobEventResponse.model_validate(event, from_attributes=True)


def _worker_response(
    worker: WorkerRecord, *, now: datetime, offline_after_seconds: float
) -> WorkerResponse:
    heartbeat = worker.last_heartbeat_at
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=UTC)
    stale = heartbeat < now - timedelta(seconds=offline_after_seconds)
    return WorkerResponse.model_validate(
        {
            **{
                name: getattr(worker, name)
                for name in WorkerResponse.model_fields
                if name != "status"
            },
            "status": WorkerStatus.OFFLINE if stale else worker.status,
        }
    )
