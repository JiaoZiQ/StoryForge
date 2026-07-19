"""Application orchestration for resumable, idempotent whole-book execution."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from decimal import Decimal

from sqlalchemy import func, select

from storyforge.application.factory import DomainServiceFactory
from storyforge.book import BookChapterScheduler
from storyforge.book.models import BookCritique
from storyforge.book.transitions import transition_book_run
from storyforge.database import SessionFactory
from storyforge.enums import (
    BookRevisionStatus,
    BookRunStatus,
    JobEventType,
    JobStatus,
    JobType,
    ProviderCallStatus,
    WorkflowRunStatus,
)
from storyforge.exceptions import (
    InvalidStateError,
    JobCancellationRequested,
    JobPauseRequested,
)
from storyforge.jobs.registry import JobRegistry
from storyforge.models import (
    BookRun,
    Chapter,
    Job,
    JobEvent,
    ProviderCall,
)
from storyforge.repositories import (
    BookEvaluationRepository,
    BookRevisionPlanRepository,
    BookRunRepository,
    ChapterRepository,
    JobEventRepository,
    JobRepository,
)
from storyforge.services.books import PeriodicBookChecker
from storyforge.settings import Settings
from storyforge.workflows import ChapterWorkflowRequest


class BookWorkflowApplicationService:
    """Advance a BookRun from durable state while reusing chapter workflow services."""

    def __init__(
        self,
        session_factory: SessionFactory,
        factory: DomainServiceFactory,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._factory = factory
        self._settings = settings
        self._registry = JobRegistry()
        self._scheduler = BookChapterScheduler(
            concurrency=settings.book_chapter_concurrency,
            maximum_concurrency=4,
        )
        self._periodic_checker = PeriodicBookChecker(session_factory)

    def execute(
        self,
        run_id: int,
        *,
        control_callback: Callable[[str], None],
        progress_callback: Callable[[str, str], None],
    ) -> dict[str, object]:
        self._initialize(run_id)
        while True:
            run, chapter_numbers = self._state(run_id)
            self._sync_already_accepted(run_id)
            run, chapter_numbers = self._state(run_id)
            resuming_chapter = (
                run.current_chapter_number
                if run.workflow_run_id is not None
                and run.current_chapter_number is not None
                and run.chapter_status_map.get(str(run.current_chapter_number)) == "running"
                else None
            )
            if resuming_chapter is not None:
                chapter_number = resuming_chapter
            else:
                decision = self._scheduler.decide(
                    mode=run.mode,
                    chapter_numbers=chapter_numbers,
                    chapter_status={
                        int(key): value for key, value in run.chapter_status_map.items()
                    },
                    dependencies=None,
                    cancel_requested=run.status is BookRunStatus.CANCEL_REQUESTED,
                    pause_requested=False,
                )
                if decision.action == "cancel":
                    raise JobCancellationRequested("Book cancellation requested")
                if decision.action == "human_review":
                    self._finish_needs_review(run_id, [decision.reason])
                    return self._result(run_id)
                if decision.action == "wait":
                    raise InvalidStateError(decision.reason)
                if decision.action == "complete":
                    break
                scheduled_chapter = decision.chapter_number
                if scheduled_chapter is None:
                    raise InvalidStateError("Scheduler returned no chapter to execute")
                chapter_number = scheduled_chapter
                self._budget_gate(run_id, estimated_calls=5, estimated_tokens=30_000)
            step = f"schedule_chapter_{chapter_number}"
            control_callback(step)
            progress_callback("started", step)
            status = self._execute_chapter(
                run_id,
                chapter_number,
                control_callback=control_callback,
                progress_callback=progress_callback,
            )
            progress_callback("completed", step)
            if status is WorkflowRunStatus.COMPLETED_NEEDS_REVIEW:
                self._finish_needs_review(
                    run_id, [f"Chapter {chapter_number} requires human review"]
                )
                return self._result(run_id)
            if status is WorkflowRunStatus.PAUSED:
                raise JobPauseRequested("Chapter workflow paused at a safe node")
            if status is not WorkflowRunStatus.COMPLETED:
                raise InvalidStateError(
                    f"Chapter {chapter_number} workflow ended in status {status}"
                )
            if chapter_number % self._settings.book_global_check_interval == 0:
                control_callback("periodic_global_check")
                summary = self._periodic_checker.check(run_id)
                self._record_periodic_check(run_id, summary)

        control_callback("build_book_snapshot")
        self._set_global_review(run_id)
        with self._factory.provider(
            "book_critic",
            project_id=run.project_id,
            idempotency_scope=f"book-run:{run.id}",
        ) as provider:
            analysis_service = self._factory.book_analysis_service(provider)
            snapshot = analysis_service.build_snapshot(run_id)
            control_callback("run_global_analysis")
            analysis, evaluation, evaluation_id = analysis_service.analyze(snapshot.id)
            if evaluation.passed:
                analysis_service.accept_snapshot(snapshot.id)
                self._finish_completed(run_id, snapshot.id)
                return self._result(
                    run_id,
                    extra={
                        "book_evaluation_id": evaluation_id,
                        "book_score": evaluation.final_score,
                        "timeline_events": len(analysis.timeline.events),
                    },
                )
            self._handle_revision_or_review(
                run_id,
                snapshot.id,
                evaluation_id,
                analysis_service,
            )
        return self._result(run_id)

    def _initialize(self, run_id: int) -> None:
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is None:
                raise InvalidStateError(f"Book run {run_id} was not found")
            if run.status is BookRunStatus.PENDING:
                transition_book_run(run, BookRunStatus.PLANNING_VALIDATION)
                self._node(run, "initialize_book_run")
                chapters = ChapterRepository(session).list_for_project(run.project_id)
                self._scheduler.validate_plan([item.chapter_number for item in chapters])
                transition_book_run(run, BookRunStatus.GENERATING)
                self._node(run, "validate_plan")
            elif run.status is BookRunStatus.PLANNING_VALIDATION:
                chapters = ChapterRepository(session).list_for_project(run.project_id)
                self._scheduler.validate_plan([item.chapter_number for item in chapters])
                transition_book_run(run, BookRunStatus.GENERATING)
                self._node(run, "validate_plan")
            elif run.status in {
                BookRunStatus.PAUSED,
                BookRunStatus.BUDGET_BLOCKED,
            }:
                target = (
                    BookRunStatus.GLOBAL_REVIEW
                    if run.completed_chapters == run.total_chapters
                    else BookRunStatus.GENERATING
                )
                transition_book_run(run, target)
            elif run.status not in {BookRunStatus.GENERATING, BookRunStatus.GLOBAL_REVIEW}:
                raise InvalidStateError(f"Book run in status {run.status} cannot execute")

    def _state(self, run_id: int) -> tuple[BookRun, list[int]]:
        with self._session_factory() as session:
            run = BookRunRepository(session).get(run_id)
            if run is None:
                raise InvalidStateError(f"Book run {run_id} was not found")
            chapters = ChapterRepository(session).list_for_project(run.project_id)
            session.expunge(run)
            return run, [item.chapter_number for item in chapters]

    def _sync_already_accepted(self, run_id: int) -> None:
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is None:
                return
            statuses = dict(run.chapter_status_map)
            for chapter in ChapterRepository(session).list_for_project(run.project_id):
                if chapter.accepted_version_id is not None:
                    statuses[str(chapter.chapter_number)] = "accepted"
            run.chapter_status_map = statuses
            run.accepted_chapters = sum(value == "accepted" for value in statuses.values())
            run.completed_chapters = run.accepted_chapters + sum(
                value in {"failed", "needs_review"} for value in statuses.values()
            )
            run.progress = round(run.completed_chapters / run.total_chapters * 75)

    def _execute_chapter(
        self,
        run_id: int,
        chapter_number: int,
        *,
        control_callback: Callable[[str], None],
        progress_callback: Callable[[str, str], None],
    ) -> WorkflowRunStatus:
        run, _ = self._state(run_id)
        self._mark_chapter_running(run_id, chapter_number)
        with self._factory.provider(
            "workflow", project_id=run.project_id, chapter_number=chapter_number
        ) as provider:
            service = self._factory.workflow_service(
                provider,
                control_callback=control_callback,
                progress_callback=progress_callback,
                initialized_callback=lambda session, workflow_id: self._link_workflow(
                    session, run_id, workflow_id
                ),
            )
            current_workflow_id = self._current_workflow(run_id, chapter_number)
            if current_workflow_id is None:
                result = service.run(
                    ChapterWorkflowRequest(
                        project_id=run.project_id,
                        chapter_number=chapter_number,
                        operation="generate",
                        max_revision_attempts=run.max_chapter_retries,
                    )
                )
            else:
                current = service.get_status(current_workflow_id)
                if current.status is WorkflowRunStatus.PAUSED:
                    result = service.resume(current_workflow_id)
                elif current.status in {
                    WorkflowRunStatus.COMPLETED,
                    WorkflowRunStatus.COMPLETED_NEEDS_REVIEW,
                }:
                    result = current
                else:
                    raise InvalidStateError(
                        f"Chapter workflow {current_workflow_id} is not safely resumable"
                    )
        if result.status is not WorkflowRunStatus.PAUSED:
            self._record_chapter_completion(
                run_id, chapter_number, result.workflow_run_id, result.status
            )
            self._update_usage(run_id, result.workflow_run_id)
        return result.status

    def _current_workflow(self, run_id: int, chapter_number: int) -> int | None:
        with self._session_factory() as session:
            run = BookRunRepository(session).get(run_id)
            if run is None or run.current_chapter_number != chapter_number:
                return None
            return run.workflow_run_id

    @staticmethod
    def _link_workflow(session: object, run_id: int, workflow_id: int) -> None:
        from sqlalchemy.orm import Session

        if not isinstance(session, Session):
            raise TypeError("Workflow initialization requires a SQLAlchemy session")
        run = BookRunRepository(session).get_for_update(run_id)
        if run is None:
            raise InvalidStateError("Book run disappeared while linking chapter workflow")
        run.workflow_run_id = workflow_id
        if run.job_id is not None:
            job = JobRepository(session).get_for_update(run.job_id)
            if job is not None:
                job.workflow_run_id = workflow_id

    def _mark_chapter_running(self, run_id: int, chapter_number: int) -> None:
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is None:
                raise InvalidStateError("Book run was not found")
            statuses = dict(run.chapter_status_map)
            statuses[str(chapter_number)] = "running"
            run.chapter_status_map = statuses
            run.current_chapter_number = chapter_number
            self._node(run, f"schedule_chapter_{chapter_number}")

    def _record_chapter_completion(
        self,
        run_id: int,
        chapter_number: int,
        workflow_run_id: int,
        status: WorkflowRunStatus,
    ) -> None:
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is None:
                raise InvalidStateError("Book run was not found")
            top_job = JobRepository(session).get_for_update(run.job_id) if run.job_id else None
            if top_job is not None:
                top_job.workflow_run_id = None
            child_key = hashlib.sha256(
                f"book:{run.id}:chapter:{chapter_number}:workflow:{workflow_run_id}".encode()
            ).hexdigest()
            child = JobRepository(session).get_by_idempotency_key(child_key)
            if child is None:
                definition = self._registry.get(JobType.RUN_CHAPTER_WORKFLOW)
                chapter = ChapterRepository(session).get_by_number(run.project_id, chapter_number)
                if chapter is None:
                    raise InvalidStateError("Scheduled chapter disappeared")
                child = JobRepository(session).add(
                    Job(
                        project_id=run.project_id,
                        chapter_id=chapter.id,
                        workflow_run_id=workflow_run_id,
                        book_run_id=run.id,
                        parent_job_id=run.job_id,
                        job_type=JobType.RUN_CHAPTER_WORKFLOW,
                        queue_name=f"{self._settings.queue_prefix}.{definition.queue_name.rsplit('.', 1)[-1]}",
                        status=JobStatus.SUCCEEDED,
                        priority=5,
                        idempotency_key=child_key,
                        payload={
                            "book_run_id": run.id,
                            "chapter_number": chapter_number,
                            "operation": "generate",
                        },
                        result={
                            "workflow_run_id": workflow_run_id,
                            "status": status.value,
                        },
                        progress=100,
                        current_step="completed",
                        max_attempts=definition.max_attempts,
                    )
                )
                JobEventRepository(session).add_ordered(
                    JobEvent(
                        job_id=child.id,
                        sequence=0,
                        event_type=JobEventType.JOB_SUCCEEDED,
                        status=JobStatus.SUCCEEDED,
                        step="completed",
                        progress=100,
                        message_code="book.chapter_completed",
                        message="Book chapter workflow completed",
                        attempt=1,
                        workflow_event_id=None,
                    )
                )
            statuses = dict(run.chapter_status_map)
            statuses[str(chapter_number)] = (
                "accepted" if status is WorkflowRunStatus.COMPLETED else "needs_review"
            )
            job_map = dict(run.chapter_job_map)
            job_map[str(chapter_number)] = child.id
            run.chapter_status_map = statuses
            run.chapter_job_map = job_map
            run.workflow_run_id = None
            run.completed_chapters = sum(
                value in {"accepted", "failed", "needs_review"} for value in statuses.values()
            )
            run.accepted_chapters = sum(value == "accepted" for value in statuses.values())
            run.needs_review_chapters = sum(value == "needs_review" for value in statuses.values())
            run.progress = round(run.completed_chapters / run.total_chapters * 75)

    def _budget_gate(self, run_id: int, *, estimated_calls: int, estimated_tokens: int) -> None:
        blocked = False
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is None:
                raise InvalidStateError("Book run was not found")
            if (
                run.provider_calls + estimated_calls > run.max_provider_calls
                or run.used_tokens + estimated_tokens > run.max_total_tokens
                or run.spent_cost > run.max_estimated_cost
            ):
                transition_book_run(run, BookRunStatus.BUDGET_BLOCKED)
                run.blocking_reasons = ["Book budget must be increased before continuing"]
                run.current_node = "budget_blocked"
                blocked = True
        if blocked:
            raise JobPauseRequested("Book budget blocked at a safe boundary")

    def _update_usage(self, run_id: int, workflow_run_id: int) -> None:
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is None:
                return
            calls = int(
                session.scalar(
                    select(func.count(ProviderCall.id)).where(
                        ProviderCall.workflow_run_id == workflow_run_id,
                        ProviderCall.status == ProviderCallStatus.SUCCEEDED,
                    )
                )
                or 0
            )
            tokens = int(
                session.scalar(
                    select(func.coalesce(func.sum(ProviderCall.total_tokens), 0)).where(
                        ProviderCall.workflow_run_id == workflow_run_id,
                        ProviderCall.status == ProviderCallStatus.SUCCEEDED,
                    )
                )
                or 0
            )
            cost = session.scalar(
                select(func.coalesce(func.sum(ProviderCall.estimated_cost), 0)).where(
                    ProviderCall.workflow_run_id == workflow_run_id,
                    ProviderCall.status == ProviderCallStatus.SUCCEEDED,
                )
            )
            # Recompute from all linked chapter workflows so replay never double-counts usage.
            workflow_ids = list(
                session.scalars(
                    select(Job.workflow_run_id).where(
                        Job.book_run_id == run.id,
                        Job.parent_job_id == run.job_id,
                        Job.workflow_run_id.is_not(None),
                    )
                )
            )
            if workflow_run_id not in workflow_ids:
                workflow_ids.append(workflow_run_id)
            aggregate = session.execute(
                select(
                    func.count(ProviderCall.id),
                    func.coalesce(func.sum(ProviderCall.total_tokens), 0),
                    func.coalesce(func.sum(ProviderCall.estimated_cost), 0),
                ).where(
                    ProviderCall.workflow_run_id.in_(workflow_ids),
                    ProviderCall.status == ProviderCallStatus.SUCCEEDED,
                )
            ).one()
            run.provider_calls = int(aggregate[0] or calls)
            run.used_tokens = int(aggregate[1] or tokens)
            run.spent_cost = Decimal(aggregate[2] or cost or 0)

    def _set_global_review(self, run_id: int) -> None:
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is None:
                raise InvalidStateError("Book run was not found")
            if run.status is BookRunStatus.GENERATING:
                transition_book_run(run, BookRunStatus.GLOBAL_REVIEW)
            run.progress = 80
            self._node(run, "build_book_snapshot")

    def _handle_revision_or_review(
        self,
        run_id: int,
        snapshot_id: int,
        evaluation_id: int,
        analysis_service: object,
    ) -> None:
        from storyforge.services.books import BookAnalysisService

        if not isinstance(analysis_service, BookAnalysisService):
            raise TypeError("Global analysis service is invalid")
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            evaluation = BookEvaluationRepository(session).get(evaluation_id)
            if run is None or evaluation is None:
                raise InvalidStateError("Global evaluation state disappeared")
            if (
                evaluation.recommended_action != "targeted_revision"
                or run.current_global_revision_round >= run.max_global_revision_rounds
            ):
                blockers = list(evaluation.blocking_reasons)
                transition_book_run(run, BookRunStatus.COMPLETED_NEEDS_REVIEW)
                run.blocking_reasons = blockers
                run.progress = 100
                needs_review = True
            else:
                transition_book_run(run, BookRunStatus.GLOBAL_REVISION)
                run.current_global_revision_round += 1
                self._node(run, "build_revision_plan")
                needs_review = False
                critique = BookCritique.model_validate(evaluation.critique)
                round_number = run.current_global_revision_round
                combined = {
                    "final_score": evaluation.final_score,
                    "passed": evaluation.passed,
                    "dimension_scores": evaluation.dimension_scores,
                    "weighted_scores": {},
                    "blocking_reasons": evaluation.blocking_reasons,
                    "recommended_action": evaluation.recommended_action,
                    "priority_chapters": evaluation.priority_chapters,
                }
                remaining_calls = run.max_provider_calls - run.provider_calls
                remaining_tokens = run.max_total_tokens - run.used_tokens
                remaining_cost = run.max_estimated_cost - run.spent_cost
        if needs_review:
            analysis_service.accept_snapshot(snapshot_id, needs_review=True)
            return
        from storyforge.book.models import BookEvaluationResult

        plan = analysis_service.build_revision_plan(
            snapshot_id=snapshot_id,
            revision_round=round_number,
            evaluation=BookEvaluationResult.model_validate(combined),
            critique=critique,
            maximum_chapters=self._settings.book_max_revision_chapters_per_round,
            remaining_calls=remaining_calls,
            remaining_tokens=remaining_tokens,
            remaining_cost=remaining_cost,
        )
        # Global changes are never silently applied: each selected chapter gets a normal
        # immutable chapter workflow with evaluate_existing semantics.
        for task in plan.chapter_tasks:
            self._execute_targeted_revision(run_id, task.chapter_number)
        with self._session_factory.begin() as session:
            revision_plan = BookRevisionPlanRepository(session).latest_for_snapshot(snapshot_id)
            run = BookRunRepository(session).get_for_update(run_id)
            if revision_plan is not None:
                revision_plan.status = BookRevisionStatus.COMPLETED
            if run is not None:
                transition_book_run(run, BookRunStatus.GLOBAL_REVIEW)
                run.impacted_chapters = {
                    str(number): "recheck_required"
                    for task in plan.chapter_tasks
                    for number in task.affected_future_chapters
                }
        revised_snapshot = analysis_service.build_snapshot(run_id)
        _, revised_evaluation, _revised_id = analysis_service.analyze(revised_snapshot.id)
        if revised_evaluation.passed:
            analysis_service.accept_snapshot(revised_snapshot.id)
            self._finish_completed(run_id, revised_snapshot.id)
        else:
            analysis_service.accept_snapshot(revised_snapshot.id, needs_review=True)
            self._finish_needs_review(run_id, revised_evaluation.blocking_reasons)

    def _execute_targeted_revision(self, run_id: int, chapter_number: int) -> None:
        run, _ = self._state(run_id)
        with self._factory.provider(
            "workflow", project_id=run.project_id, chapter_number=chapter_number
        ) as provider:
            service = self._factory.workflow_service(
                provider,
                initialized_callback=lambda session, workflow_id: self._link_workflow(
                    session, run_id, workflow_id
                ),
            )
            result = service.run(
                ChapterWorkflowRequest(
                    project_id=run.project_id,
                    chapter_number=chapter_number,
                    operation="targeted_revision",
                    max_revision_attempts=run.max_chapter_retries,
                )
            )
        if result.status is not WorkflowRunStatus.COMPLETED:
            raise InvalidStateError("Targeted chapter revision did not produce an accepted version")
        self._record_chapter_completion(
            run_id, chapter_number, result.workflow_run_id, result.status
        )
        self._update_usage(run_id, result.workflow_run_id)

    def _finish_completed(self, run_id: int, snapshot_id: int) -> None:
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is None:
                return
            transition_book_run(run, BookRunStatus.COMPLETED)
            run.book_snapshot_id = snapshot_id
            run.best_snapshot_id = snapshot_id
            run.current_node = "accept_book_snapshot"
            run.progress = 100
            run.blocking_reasons = []
            self._node(run, "accept_book_snapshot")

    def _finish_needs_review(self, run_id: int, blockers: list[str]) -> None:
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is None:
                return
            if run.status not in {
                BookRunStatus.COMPLETED_NEEDS_REVIEW,
                BookRunStatus.COMPLETED,
            }:
                transition_book_run(run, BookRunStatus.COMPLETED_NEEDS_REVIEW)
            run.current_node = "mark_book_needs_review"
            run.progress = 100
            run.blocking_reasons = list(blockers)
            self._node(run, "mark_book_needs_review")

    def _append_node(self, run_id: int, node: str) -> None:
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is not None:
                self._node(run, node)

    def _record_periodic_check(self, run_id: int, summary: dict[str, object]) -> None:
        critical_conflicts = summary.get("critical_conflicts", 0)
        blocked = isinstance(critical_conflicts, int | float) and critical_conflicts > 0
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is None:
                raise InvalidStateError("Book run disappeared during periodic analysis")
            run.periodic_checks = [*run.periodic_checks, summary]
            self._node(run, "periodic_global_check")
            if blocked:
                transition_book_run(run, BookRunStatus.PAUSED)
                run.blocking_reasons = ["A critical periodic timeline conflict requires review"]
        if blocked:
            raise JobPauseRequested("Critical periodic global conflict")

    @staticmethod
    def _node(run: BookRun, node: str) -> None:
        history = list(run.node_history)
        history.append(node)
        run.node_history = history
        run.current_node = node

    def _result(self, run_id: int, *, extra: dict[str, object] | None = None) -> dict[str, object]:
        with self._session_factory() as session:
            run = BookRunRepository(session).get(run_id)
            if run is None:
                raise InvalidStateError("Book run was not found")
            result: dict[str, object] = {
                "book_run_id": run.id,
                "status": run.status.value,
                "completed_chapters": run.completed_chapters,
                "accepted_chapters": run.accepted_chapters,
                "chapter_revisions": self._revision_count(session, run.project_id),
                "global_revision_rounds": run.current_global_revision_round,
                "snapshot_id": run.book_snapshot_id,
            }
            result.update(extra or {})
            return result

    @staticmethod
    def _revision_count(session: object, project_id: int) -> int:
        from sqlalchemy.orm import Session

        if not isinstance(session, Session):
            return 0
        value = session.scalar(
            select(func.count())
            .select_from(Chapter)
            .where(
                Chapter.project_id == project_id,
                Chapter.version > 1,
            )
        )
        return int(value or 0)
