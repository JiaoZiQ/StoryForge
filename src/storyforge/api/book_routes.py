"""Thin HTTP and SSE adapters for full-book runs and frozen analyses."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import StreamingResponse

from storyforge.exceptions import InvalidStateError, QueueBackpressureError
from storyforge.jobs.broker import RedisEventBus
from storyforge.jobs.transitions import TERMINAL_JOB_STATUSES
from storyforge.schemas.books import (
    BookAnalysisResponse,
    BookEvaluationResponse,
    BookRevisionPlanResponse,
    BookRunAcceptedResponse,
    BookRunCreateRequest,
    BookRunPageResponse,
    BookRunResponse,
    BookRunResumeRequest,
    BookSnapshotPageResponse,
    BookSnapshotResponse,
    TimelinePageResponse,
)
from storyforge.schemas.jobs import JobEventPageResponse

from .dependencies import BookQueryServiceDep, BookRunServiceDep, JobServiceDep
from .errors import ERROR_RESPONSES

book_router = APIRouter(responses=ERROR_RESPONSES)


@book_router.post(
    "/projects/{project_id}/book-runs",
    response_model=BookRunAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["books"],
    operation_id="create_book_run",
)
def create_book_run(
    project_id: int,
    payload: BookRunCreateRequest,
    service: BookRunServiceDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> BookRunAcceptedResponse:
    return service.create(project_id, payload, external_idempotency_key=idempotency_key)


@book_router.get(
    "/projects/{project_id}/book-runs",
    response_model=BookRunPageResponse,
    tags=["books"],
    operation_id="list_book_runs",
)
def list_book_runs(
    project_id: int,
    service: BookRunServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> BookRunPageResponse:
    return service.list_project(project_id, page=page, page_size=page_size)


@book_router.get(
    "/book-runs/{book_run_id}",
    response_model=BookRunResponse,
    tags=["books"],
    operation_id="get_book_run",
)
def get_book_run(book_run_id: int, service: BookRunServiceDep) -> BookRunResponse:
    return service.get(book_run_id)


@book_router.post(
    "/book-runs/{book_run_id}/pause",
    response_model=BookRunResponse,
    tags=["books"],
    operation_id="pause_book_run",
)
def pause_book_run(book_run_id: int, service: BookRunServiceDep) -> BookRunResponse:
    return service.request_pause(book_run_id)


@book_router.post(
    "/book-runs/{book_run_id}/resume",
    response_model=BookRunResponse,
    tags=["books"],
    operation_id="resume_book_run",
)
def resume_book_run(
    book_run_id: int,
    payload: BookRunResumeRequest,
    service: BookRunServiceDep,
) -> BookRunResponse:
    return service.resume(book_run_id, payload)


@book_router.post(
    "/book-runs/{book_run_id}/cancel",
    response_model=BookRunResponse,
    tags=["books"],
    operation_id="cancel_book_run",
)
def cancel_book_run(book_run_id: int, service: BookRunServiceDep) -> BookRunResponse:
    return service.request_cancel(book_run_id)


@book_router.get(
    "/book-runs/{book_run_id}/events",
    response_model=JobEventPageResponse,
    tags=["books"],
    operation_id="list_book_run_events",
)
def list_book_run_events(
    book_run_id: int,
    runs: BookRunServiceDep,
    jobs: JobServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
) -> JobEventPageResponse:
    run = runs.get(book_run_id)
    if run.job_id is None:
        raise InvalidStateError("BookRun has no top-level Job")
    return jobs.events(run.job_id, page=page, page_size=page_size)


@book_router.get(
    "/book-runs/{book_run_id}/events/stream",
    response_class=StreamingResponse,
    tags=["books"],
    operation_id="stream_book_run_events",
)
async def stream_book_run_events(
    book_run_id: int,
    request: Request,
    runs: BookRunServiceDep,
    jobs: JobServiceDep,
    last_event_id: Annotated[int | None, Header(alias="Last-Event-ID", ge=0)] = None,
) -> StreamingResponse:
    run = runs.get(book_run_id)
    if run.job_id is None:
        raise InvalidStateError("BookRun has no top-level Job")
    job_id = run.job_id
    jobs.get(job_id)
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
                for event in jobs.events_after(job_id, cursor):
                    emitted = True
                    cursor = event.id
                    payload = event.model_dump(mode="json")
                    payload["event_id"] = event.id
                    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                    yield f"id: {event.id}\nevent: {event.event_type.value}\ndata: {data}\n\n"
                job = jobs.get(job_id)
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
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@book_router.get(
    "/projects/{project_id}/book-snapshots",
    response_model=BookSnapshotPageResponse,
    tags=["books"],
    operation_id="list_book_snapshots",
)
def list_book_snapshots(project_id: int, service: BookQueryServiceDep) -> BookSnapshotPageResponse:
    return service.snapshots(project_id)


@book_router.get(
    "/book-snapshots/{snapshot_id}",
    response_model=BookSnapshotResponse,
    tags=["books"],
    operation_id="get_book_snapshot",
)
def get_book_snapshot(snapshot_id: int, service: BookQueryServiceDep) -> BookSnapshotResponse:
    return service.snapshot(snapshot_id)


@book_router.get(
    "/book-snapshots/{snapshot_id}/evaluation",
    response_model=BookEvaluationResponse,
    tags=["books"],
    operation_id="get_book_evaluation",
)
def get_book_evaluation(snapshot_id: int, service: BookQueryServiceDep) -> BookEvaluationResponse:
    return service.evaluation(snapshot_id)


@book_router.get(
    "/book-snapshots/{snapshot_id}/timeline",
    response_model=TimelinePageResponse,
    tags=["books"],
    operation_id="get_book_timeline",
)
def get_book_timeline(
    snapshot_id: int,
    service: BookQueryServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
) -> TimelinePageResponse:
    return service.timeline(snapshot_id, page=page, page_size=page_size)


@book_router.get(
    "/book-snapshots/{snapshot_id}/character-arcs",
    response_model=BookAnalysisResponse,
    tags=["books"],
    operation_id="get_book_character_arcs",
)
def get_book_character_arcs(snapshot_id: int, service: BookQueryServiceDep) -> BookAnalysisResponse:
    return service.character_arcs(snapshot_id)


@book_router.get(
    "/book-snapshots/{snapshot_id}/relationships",
    response_model=BookAnalysisResponse,
    tags=["books"],
    operation_id="get_book_relationships",
)
def get_book_relationships(snapshot_id: int, service: BookQueryServiceDep) -> BookAnalysisResponse:
    return service.relationships(snapshot_id)


@book_router.get(
    "/book-snapshots/{snapshot_id}/foreshadowing",
    response_model=BookAnalysisResponse,
    tags=["books"],
    operation_id="get_book_foreshadowing",
)
def get_book_foreshadowing(snapshot_id: int, service: BookQueryServiceDep) -> BookAnalysisResponse:
    return service.foreshadowing(snapshot_id)


@book_router.get(
    "/book-snapshots/{snapshot_id}/pacing",
    response_model=BookAnalysisResponse,
    tags=["books"],
    operation_id="get_book_pacing",
)
def get_book_pacing(snapshot_id: int, service: BookQueryServiceDep) -> BookAnalysisResponse:
    return service.pacing(snapshot_id)


@book_router.get(
    "/book-snapshots/{snapshot_id}/transitions",
    response_model=BookAnalysisResponse,
    tags=["books"],
    operation_id="get_book_transitions",
)
def get_book_transitions(snapshot_id: int, service: BookQueryServiceDep) -> BookAnalysisResponse:
    return service.transitions(snapshot_id)


@book_router.get(
    "/book-snapshots/{snapshot_id}/revision-plan",
    response_model=BookRevisionPlanResponse,
    tags=["books"],
    operation_id="get_book_revision_plan",
)
def get_book_revision_plan(
    snapshot_id: int, service: BookQueryServiceDep
) -> BookRevisionPlanResponse:
    return service.revision_plan(snapshot_id)
