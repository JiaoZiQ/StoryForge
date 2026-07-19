"""Thin async-job HTTP routes and replayable SSE progress stream."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import StreamingResponse

from storyforge.enums import JobStatus, JobType
from storyforge.exceptions import QueueBackpressureError
from storyforge.jobs.broker import RedisEventBus
from storyforge.jobs.transitions import TERMINAL_JOB_STATUSES
from storyforge.schemas.api import (
    EvaluateChapterRequest,
    GenerateChapterRequest,
    GeneratePlanRequest,
    MemoryReindexRequest,
    StartWorkflowRequest,
)
from storyforge.schemas.jobs import (
    JobAcceptedResponse,
    JobCreateRequest,
    JobEventPageResponse,
    JobPageResponse,
    JobResponse,
    QueueHealthResponse,
    WorkerResponse,
)

from .dependencies import JobServiceDep
from .errors import ERROR_RESPONSES

job_router = APIRouter(responses=ERROR_RESPONSES)


@job_router.post(
    "/jobs",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["jobs"],
    summary="Create an idempotent asynchronous job",
    operation_id="create_job",
)
def create_job(payload: JobCreateRequest, service: JobServiceDep) -> JobAcceptedResponse:
    return service.create(payload)


def _dedicated_request(
    *,
    job_type: JobType,
    project_id: int,
    chapter_number: int | None,
    operation: str,
    payload: dict[str, object],
    idempotency_key: str | None,
    priority: int,
) -> JobCreateRequest:
    return JobCreateRequest(
        job_type=job_type,
        project_id=project_id,
        chapter_number=chapter_number,
        operation=operation,
        payload=payload,
        idempotency_key=idempotency_key,
        priority=priority,
    )


@job_router.post(
    "/projects/{project_id}/plan/jobs",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["jobs"],
    operation_id="create_plan_job",
)
def create_plan_job(
    project_id: int,
    payload: GeneratePlanRequest,
    service: JobServiceDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    priority: Annotated[int, Query(ge=1, le=8)] = 5,
) -> JobAcceptedResponse:
    return service.create(
        _dedicated_request(
            job_type=JobType.GENERATE_PLAN,
            project_id=project_id,
            chapter_number=None,
            operation="generate",
            payload=payload.model_dump(mode="json", exclude_none=True),
            idempotency_key=idempotency_key,
            priority=priority,
        )
    )


@job_router.post(
    "/projects/{project_id}/chapters/{chapter_number}/generation-jobs",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["jobs"],
    operation_id="create_chapter_generation_job",
)
def create_chapter_generation_job(
    project_id: int,
    chapter_number: int,
    payload: GenerateChapterRequest,
    service: JobServiceDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    priority: Annotated[int, Query(ge=1, le=8)] = 5,
) -> JobAcceptedResponse:
    return service.create(
        _dedicated_request(
            job_type=JobType.GENERATE_CHAPTER,
            project_id=project_id,
            chapter_number=chapter_number,
            operation="generate",
            payload=payload.model_dump(mode="json", exclude_none=True),
            idempotency_key=idempotency_key,
            priority=priority,
        )
    )


@job_router.post(
    "/projects/{project_id}/chapters/{chapter_number}/evaluation-jobs",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["jobs"],
    operation_id="create_chapter_evaluation_job",
)
def create_chapter_evaluation_job(
    project_id: int,
    chapter_number: int,
    payload: EvaluateChapterRequest,
    service: JobServiceDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    priority: Annotated[int, Query(ge=1, le=8)] = 5,
) -> JobAcceptedResponse:
    return service.create(
        _dedicated_request(
            job_type=JobType.EVALUATE_CHAPTER,
            project_id=project_id,
            chapter_number=chapter_number,
            operation="evaluate",
            payload=payload.model_dump(mode="json", exclude_none=True),
            idempotency_key=idempotency_key,
            priority=priority,
        )
    )


@job_router.post(
    "/projects/{project_id}/chapters/{chapter_number}/workflow-jobs",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["jobs"],
    operation_id="create_chapter_workflow_job",
)
def create_chapter_workflow_job(
    project_id: int,
    chapter_number: int,
    payload: StartWorkflowRequest,
    service: JobServiceDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    priority: Annotated[int, Query(ge=1, le=8)] = 5,
) -> JobAcceptedResponse:
    return service.create(
        _dedicated_request(
            job_type=JobType.RUN_CHAPTER_WORKFLOW,
            project_id=project_id,
            chapter_number=chapter_number,
            operation=payload.operation.value,
            payload=payload.model_dump(mode="json", exclude_none=True),
            idempotency_key=idempotency_key,
            priority=priority,
        )
    )


@job_router.post(
    "/projects/{project_id}/memory/reindex-jobs",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["jobs"],
    operation_id="create_memory_reindex_job",
)
def create_memory_reindex_job(
    project_id: int,
    payload: MemoryReindexRequest,
    service: JobServiceDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    priority: Annotated[int, Query(ge=1, le=8)] = 5,
) -> JobAcceptedResponse:
    return service.create(
        _dedicated_request(
            job_type=JobType.REINDEX_MEMORY,
            project_id=project_id,
            chapter_number=None,
            operation="reindex",
            payload=payload.model_dump(mode="json", exclude_none=True),
            idempotency_key=idempotency_key,
            priority=priority,
        )
    )


@job_router.get(
    "/jobs",
    response_model=JobPageResponse,
    tags=["jobs"],
    summary="Filter durable jobs",
    operation_id="list_jobs",
)
def list_jobs(
    service: JobServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    job_type: JobType | None = None,
    project_id: int | None = None,
    chapter_id: int | None = None,
    chapter_number: Annotated[int | None, Query(ge=1)] = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> JobPageResponse:
    return service.list_jobs(
        page=page,
        page_size=page_size,
        status=job_status,
        job_type=job_type,
        project_id=project_id,
        chapter_id=chapter_id,
        chapter_number=chapter_number,
        created_from=created_from,
        created_to=created_to,
    )


@job_router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    tags=["jobs"],
    summary="Get safe job detail",
    operation_id="get_job",
)
def get_job(job_id: int, service: JobServiceDep) -> JobResponse:
    return service.get(job_id)


@job_router.get(
    "/jobs/{job_id}/events",
    response_model=JobEventPageResponse,
    tags=["jobs"],
    summary="List durable job progress events",
    operation_id="list_job_events",
)
def list_job_events(
    job_id: int,
    service: JobServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
) -> JobEventPageResponse:
    return service.events(job_id, page=page, page_size=page_size)


@job_router.get(
    "/jobs/{job_id}/events/stream",
    response_class=StreamingResponse,
    tags=["jobs"],
    summary="Replay and follow job events using SSE",
    operation_id="stream_job_events",
)
async def stream_job_events(
    job_id: int,
    request: Request,
    service: JobServiceDep,
    last_event_id: Annotated[int | None, Header(alias="Last-Event-ID", ge=0)] = None,
) -> StreamingResponse:
    service.get(job_id)
    settings = request.app.state.settings
    semaphore: asyncio.Semaphore = request.app.state.sse_semaphore
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=0.01)
    except TimeoutError as exc:
        raise QueueBackpressureError("SSE connection limit reached") from exc
    event_bus = (
        RedisEventBus(settings.redis_url, prefix=settings.queue_prefix)
        if settings.job_execution_mode == "queue"
        else None
    )

    async def stream() -> AsyncIterator[str]:
        try:
            cursor = last_event_id
            while True:
                emitted = False
                for event in service.events_after(job_id, cursor):
                    emitted = True
                    cursor = event.id
                    payload = event.model_dump(mode="json")
                    payload["event_id"] = event.id
                    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                    yield f"id: {event.id}\nevent: {event.event_type.value}\ndata: {data}\n\n"
                job = service.get(job_id)
                if job.status in TERMINAL_JOB_STATUSES:
                    return
                if await request.is_disconnected():
                    return
                if not emitted:
                    notified = (
                        await asyncio.to_thread(
                            event_bus.wait_once,
                            job_id,
                            timeout_seconds=settings.sse_heartbeat_seconds,
                        )
                        if event_bus is not None
                        else None
                    )
                    if notified is None:
                        yield ": heartbeat\n\n"
                        if event_bus is None:
                            await asyncio.sleep(settings.sse_heartbeat_seconds)
        finally:
            semaphore.release()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@job_router.post(
    "/jobs/{job_id}/cancel", response_model=JobResponse, tags=["jobs"], operation_id="cancel_job"
)
def cancel_job(job_id: int, service: JobServiceDep) -> JobResponse:
    return service.cancel(job_id)


@job_router.post(
    "/jobs/{job_id}/pause", response_model=JobResponse, tags=["jobs"], operation_id="pause_job"
)
def pause_job(job_id: int, service: JobServiceDep) -> JobResponse:
    return service.pause(job_id)


@job_router.post(
    "/jobs/{job_id}/resume", response_model=JobResponse, tags=["jobs"], operation_id="resume_job"
)
def resume_job(job_id: int, service: JobServiceDep) -> JobResponse:
    return service.resume(job_id)


@job_router.post(
    "/jobs/{job_id}/retry", response_model=JobResponse, tags=["jobs"], operation_id="retry_job"
)
def retry_job(job_id: int, service: JobServiceDep) -> JobResponse:
    return service.retry(job_id)


@job_router.post(
    "/jobs/{job_id}/discard", response_model=JobResponse, tags=["jobs"], operation_id="discard_job"
)
def discard_job(job_id: int, service: JobServiceDep) -> JobResponse:
    return service.discard(job_id)


@job_router.get(
    "/dead-letter-jobs",
    response_model=JobPageResponse,
    tags=["jobs"],
    operation_id="list_dead_letter_jobs",
)
def list_dead_letter_jobs(
    service: JobServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    project_id: int | None = None,
) -> JobPageResponse:
    return service.list_jobs(
        page=page,
        page_size=page_size,
        status=JobStatus.DEAD_LETTERED,
        project_id=project_id,
    )


@job_router.post(
    "/dead-letter-jobs/{job_id}/retry",
    response_model=JobResponse,
    tags=["jobs"],
    operation_id="retry_dead_letter_job",
)
def retry_dead_letter_job(job_id: int, service: JobServiceDep) -> JobResponse:
    return service.retry(job_id)


@job_router.post(
    "/dead-letter-jobs/{job_id}/discard",
    response_model=JobResponse,
    tags=["jobs"],
    operation_id="discard_dead_letter_job",
)
def discard_dead_letter_job(job_id: int, service: JobServiceDep) -> JobResponse:
    return service.discard(job_id)


@job_router.get(
    "/workers",
    response_model=list[WorkerResponse],
    tags=["jobs"],
    operation_id="list_workers",
)
def list_workers(request: Request, service: JobServiceDep) -> list[WorkerResponse]:
    return _queue_health(request, service).workers


@job_router.get(
    "/workers/health",
    response_model=QueueHealthResponse,
    tags=["jobs"],
    operation_id="get_workers_health",
)
def workers_health(request: Request, service: JobServiceDep) -> QueueHealthResponse:
    return _queue_health(request, service)


@job_router.get(
    "/queue/health",
    response_model=QueueHealthResponse,
    tags=["jobs"],
    operation_id="get_queue_health",
)
def queue_health(request: Request, service: JobServiceDep) -> QueueHealthResponse:
    return _queue_health(request, service)


def _queue_health(request: Request, service: JobServiceDep) -> QueueHealthResponse:
    settings = request.app.state.settings
    reachable = settings.job_execution_mode == "inline"
    if not reachable:
        from storyforge.jobs.broker import DramatiqJobBroker

        reachable = DramatiqJobBroker(settings.redis_url, namespace=settings.queue_prefix).ping()
    return service.health(reachable)
