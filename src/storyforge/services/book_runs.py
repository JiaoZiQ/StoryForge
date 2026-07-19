"""Transactional admission and control service for full-book asynchronous runs."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from storyforge.book.transitions import TERMINAL_BOOK_RUN_STATUSES, transition_book_run
from storyforge.database import SessionFactory
from storyforge.enums import (
    BookRunStatus,
    JobEventType,
    JobStatus,
    JobType,
    OutboxStatus,
)
from storyforge.exceptions import EntityNotFoundError, InvalidStateError
from storyforge.jobs.registry import JobRegistry
from storyforge.models import BookRun, Job, JobEvent, OutboxMessage
from storyforge.repositories import (
    BookRunRepository,
    ChapterRepository,
    JobEventRepository,
    JobRepository,
    OutboxRepository,
    ProjectRepository,
)
from storyforge.schemas.books import (
    BookRunAcceptedResponse,
    BookRunCreateRequest,
    BookRunPageResponse,
    BookRunResponse,
    BookRunResumeRequest,
)
from storyforge.services.jobs import JobService
from storyforge.settings import Settings


class BookRunService:
    """Own BookRun/Job/Outbox transactions and expose content-free projections."""

    def __init__(self, session_factory: SessionFactory, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._jobs = JobService(session_factory, settings)
        self._registry = JobRegistry()

    def create(
        self,
        project_id: int,
        request: BookRunCreateRequest,
        *,
        external_idempotency_key: str | None,
    ) -> BookRunAcceptedResponse:
        """Atomically create the BookRun, top Job, first event, and Outbox message."""
        key = self._idempotency_key(project_id, request, external_idempotency_key)
        with self._session_factory() as lookup:
            existing = BookRunRepository(lookup).by_idempotency_key(key)
            if existing is not None:
                if existing.job_id is None:
                    raise InvalidStateError("Existing BookRun is missing its top-level Job")
                return self._accepted(existing, reused=True)
        try:
            with self._session_factory.begin() as session:
                project = ProjectRepository(session).get(project_id)
                if project is None:
                    raise EntityNotFoundError(f"Project {project_id} was not found")
                chapters = ChapterRepository(session).list_for_project(project_id)
                if len(chapters) != project.target_chapters:
                    raise InvalidStateError(
                        "BookRun requires a complete, continuous project chapter plan"
                    )
                if [chapter.chapter_number for chapter in chapters] != list(
                    range(1, project.target_chapters + 1)
                ):
                    raise InvalidStateError("Project chapter numbers must be continuous")
                active = BookRunRepository(session).active_for_project(project_id)
                if active is not None:
                    if external_idempotency_key:
                        return self._accepted(active, reused=True)
                    raise InvalidStateError(f"Project already has active BookRun {active.id}")
                run = BookRunRepository(session).add(
                    BookRun(
                        project_id=project_id,
                        status=BookRunStatus.PENDING,
                        mode=request.mode,
                        idempotency_key=key,
                        total_chapters=project.target_chapters,
                        completed_chapters=0,
                        accepted_chapters=0,
                        failed_chapters=0,
                        needs_review_chapters=0,
                        max_chapter_retries=(
                            request.max_chapter_retries
                            if request.max_chapter_retries is not None
                            else self._settings.book_max_chapter_retries
                        ),
                        max_global_revision_rounds=(
                            request.max_global_revision_rounds
                            if request.max_global_revision_rounds is not None
                            else self._settings.book_max_global_revision_rounds
                        ),
                        model_profile=request.model_profile or project.model_profile,
                        privacy_policy=request.privacy_policy or project.privacy_policy,
                        max_estimated_cost=(
                            request.max_estimated_cost
                            if request.max_estimated_cost is not None
                            else self._settings.book_max_cost
                        ),
                        max_total_tokens=(
                            request.max_total_tokens
                            if request.max_total_tokens is not None
                            else self._settings.book_max_tokens
                        ),
                        max_provider_calls=(
                            request.max_provider_calls
                            if request.max_provider_calls is not None
                            else self._settings.book_max_provider_calls
                        ),
                        chapter_status_map={
                            str(chapter.chapter_number): "planned" for chapter in chapters
                        },
                    )
                )
                definition = self._registry.get(JobType.RUN_BOOK)
                job = JobRepository(session).add(
                    Job(
                        project_id=project_id,
                        chapter_id=None,
                        workflow_run_id=None,
                        book_run_id=run.id,
                        parent_job_id=None,
                        job_type=JobType.RUN_BOOK,
                        queue_name=f"{self._settings.queue_prefix}.{definition.queue_name.rsplit('.', 1)[-1]}",
                        status=JobStatus.OUTBOX_PENDING,
                        priority=5,
                        idempotency_key=hashlib.sha256(f"book-job:{key}".encode()).hexdigest(),
                        payload={"book_run_id": run.id},
                        payload_schema_version=1,
                        max_attempts=min(definition.max_attempts, self._settings.job_max_attempts),
                        correlation_id=str(uuid4()),
                    )
                )
                run.job_id = job.id
                JobEventRepository(session).add_ordered(
                    JobEvent(
                        job_id=job.id,
                        sequence=0,
                        event_type=JobEventType.JOB_CREATED,
                        status=job.status,
                        progress=0,
                        message_code="book_run.created",
                        message="Book run job created",
                        attempt=0,
                    )
                )
                OutboxRepository(session).add(
                    OutboxMessage(
                        aggregate_type="job",
                        aggregate_id=job.id,
                        event_type="job.enqueue",
                        payload={"job_id": job.id, "queue_name": job.queue_name},
                        status=OutboxStatus.PENDING,
                        deduplication_key=f"job:{job.id}:create",
                    )
                )
                response = self._accepted(run, reused=False)
            return response
        except IntegrityError:
            with self._session_factory() as session:
                existing = BookRunRepository(session).by_idempotency_key(key)
                if existing is not None:
                    return self._accepted(existing, reused=True)
            raise InvalidStateError("A concurrent active BookRun already exists") from None

    def get(self, run_id: int) -> BookRunResponse:
        with self._session_factory() as session:
            run = BookRunRepository(session).get(run_id)
            if run is None:
                raise EntityNotFoundError(f"Book run {run_id} was not found")
            return self._response(run)

    def list_project(self, project_id: int, *, page: int, page_size: int) -> BookRunPageResponse:
        with self._session_factory() as session:
            if ProjectRepository(session).get(project_id) is None:
                raise EntityNotFoundError(f"Project {project_id} was not found")
            result = BookRunRepository(session).page_for_project(
                project_id, page=page, page_size=page_size
            )
            items = [self._response(item) for item in result.items]
        total_pages = (result.total_items + page_size - 1) // page_size
        return BookRunPageResponse(
            items=items,
            page=page,
            page_size=page_size,
            total_items=result.total_items,
            total_pages=total_pages,
        )

    def request_pause(self, run_id: int) -> BookRunResponse:
        run = self._entity(run_id)
        if run.status not in {
            BookRunStatus.PLANNING_VALIDATION,
            BookRunStatus.GENERATING,
            BookRunStatus.GLOBAL_REVIEW,
            BookRunStatus.GLOBAL_REVISION,
        }:
            raise InvalidStateError(f"BookRun in status {run.status} cannot be paused")
        if run.job_id is None:
            raise InvalidStateError("BookRun has no top-level Job")
        job = self._jobs.request_pause(run.job_id)
        if job.status is JobStatus.PAUSED:
            self.mark_paused(run_id)
        return self.get(run_id)

    def resume(self, run_id: int, request: BookRunResumeRequest | None = None) -> BookRunResponse:
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is None:
                raise EntityNotFoundError(f"Book run {run_id} was not found")
            if run.status not in {BookRunStatus.PAUSED, BookRunStatus.BUDGET_BLOCKED}:
                raise InvalidStateError("Only paused or budget-blocked BookRuns can resume")
            if run.job_id is None:
                raise InvalidStateError("BookRun has no top-level Job")
            if request is not None:
                if request.max_estimated_cost is not None:
                    if request.max_estimated_cost < run.spent_cost:
                        raise InvalidStateError("New book cost limit is below already spent cost")
                    run.max_estimated_cost = request.max_estimated_cost
                if request.max_total_tokens is not None:
                    if request.max_total_tokens < run.used_tokens:
                        raise InvalidStateError("New token limit is below already used tokens")
                    run.max_total_tokens = request.max_total_tokens
                if request.max_provider_calls is not None:
                    if request.max_provider_calls < run.provider_calls:
                        raise InvalidStateError("New call limit is below already used calls")
                    run.max_provider_calls = request.max_provider_calls
            if run.current_node == "pending":
                target = BookRunStatus.PLANNING_VALIDATION
            else:
                target = (
                    BookRunStatus.GLOBAL_REVIEW
                    if run.completed_chapters == run.total_chapters
                    else BookRunStatus.GENERATING
                )
            transition_book_run(run, target)
            job_id = run.job_id
        self._jobs.resume(job_id)
        return self.get(run_id)

    def request_cancel(self, run_id: int) -> BookRunResponse:
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is None:
                raise EntityNotFoundError(f"Book run {run_id} was not found")
            if run.status in TERMINAL_BOOK_RUN_STATUSES:
                raise InvalidStateError(f"BookRun in status {run.status} cannot be cancelled")
            if run.status in {BookRunStatus.PAUSED, BookRunStatus.BUDGET_BLOCKED}:
                transition_book_run(run, BookRunStatus.CANCELLED)
            elif run.status is not BookRunStatus.CANCEL_REQUESTED:
                transition_book_run(run, BookRunStatus.CANCEL_REQUESTED)
            job_id = run.job_id
        if job_id is not None:
            job = self._jobs.request_cancel(job_id)
            if job.status is JobStatus.CANCELLED:
                with self._session_factory.begin() as session:
                    run = BookRunRepository(session).get_for_update(run_id)
                    if run is not None and run.status is BookRunStatus.CANCEL_REQUESTED:
                        transition_book_run(run, BookRunStatus.CANCELLED)
        return self.get(run_id)

    def mark_paused(self, run_id: int) -> None:
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if (
                run is not None
                and run.status not in TERMINAL_BOOK_RUN_STATUSES
                and run.status is not BookRunStatus.BUDGET_BLOCKED
            ):
                transition_book_run(run, BookRunStatus.PAUSED)

    def mark_cancelled(self, run_id: int) -> None:
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is not None and run.status not in TERMINAL_BOOK_RUN_STATUSES:
                if run.status is not BookRunStatus.CANCEL_REQUESTED:
                    transition_book_run(run, BookRunStatus.CANCEL_REQUESTED)
                transition_book_run(run, BookRunStatus.CANCELLED)

    def mark_failed(self, run_id: int, error: BaseException) -> None:
        code, message = self._jobs.safe_error(error)
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is not None and run.status not in TERMINAL_BOOK_RUN_STATUSES:
                transition_book_run(run, BookRunStatus.FAILED)
                run.current_node = "fail_book_run"
                run.error_code = code
                run.error_message = message

    def _entity(self, run_id: int) -> BookRun:
        with self._session_factory() as session:
            run = BookRunRepository(session).get(run_id)
            if run is None:
                raise EntityNotFoundError(f"Book run {run_id} was not found")
            session.expunge(run)
            return run

    @staticmethod
    def _idempotency_key(
        project_id: int, request: BookRunCreateRequest, external_key: str | None
    ) -> str:
        body = {
            "project_id": project_id,
            "request": request.model_dump(mode="json"),
            "external_key": external_key or "",
        }
        return hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _accepted(run: BookRun, *, reused: bool) -> BookRunAcceptedResponse:
        if run.job_id is None:
            raise InvalidStateError("BookRun admission did not create a top-level Job")
        return BookRunAcceptedResponse(
            book_run_id=run.id,
            job_id=run.job_id,
            reused=reused,
            status=run.status,
            status_url=f"/api/v1/book-runs/{run.id}",
            events_url=f"/api/v1/book-runs/{run.id}/events/stream",
        )

    @staticmethod
    def _response(run: BookRun) -> BookRunResponse:
        return BookRunResponse(
            id=run.id,
            project_id=run.project_id,
            job_id=run.job_id,
            status=run.status,
            mode=run.mode,
            total_chapters=run.total_chapters,
            completed_chapters=run.completed_chapters,
            accepted_chapters=run.accepted_chapters,
            failed_chapters=run.failed_chapters,
            needs_review_chapters=run.needs_review_chapters,
            current_chapter_number=run.current_chapter_number,
            current_global_revision_round=run.current_global_revision_round,
            max_global_revision_rounds=run.max_global_revision_rounds,
            current_node=run.current_node,
            progress=run.progress,
            book_snapshot_id=run.book_snapshot_id,
            best_snapshot_id=run.best_snapshot_id,
            blocking_reasons=list(run.blocking_reasons),
            chapter_status=dict(run.chapter_status_map),
            periodic_checks=list(run.periodic_checks),
            spent_cost=run.spent_cost,
            remaining_cost=max(Decimal("0"), run.max_estimated_cost - run.spent_cost),
            used_tokens=run.used_tokens,
            remaining_tokens=max(0, run.max_total_tokens - run.used_tokens),
            provider_calls=run.provider_calls,
            remaining_provider_calls=max(0, run.max_provider_calls - run.provider_calls),
            started_at=run.started_at,
            updated_at=run.updated_at,
            finished_at=run.finished_at,
            error_code=run.error_code,
            error_message=run.error_message,
        )
