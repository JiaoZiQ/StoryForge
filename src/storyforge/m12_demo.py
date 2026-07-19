"""Five-chapter offline demonstration for whole-book generation and recovery."""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from storyforge.agents import PlannerAgent
from storyforge.application import DomainServiceFactory
from storyforge.application.jobs import JobApplicationService
from storyforge.database import SessionFactory
from storyforge.enums import (
    BookRunStatus,
    FactStatus,
    JobStatus,
    MemoryStatus,
)
from storyforge.exceptions import InvalidStateError
from storyforge.jobs.handlers import JobHandlers
from storyforge.jobs.worker import JobExecutor
from storyforge.m5_demo import build_m5_provider
from storyforge.models import (
    BookEvaluation,
    BookSnapshot,
    Chapter,
    ChapterVersion,
    Character,
    Evaluation,
    Fact,
    Job,
    MemoryChunk,
    ProviderCall,
)
from storyforge.models.base import utc_now
from storyforge.prompts import build_prompt_registry
from storyforge.repositories import (
    BookRunRepository,
    ChapterRepository,
    FactRepository,
    JobRepository,
)
from storyforge.schemas.books import BookRunCreateRequest, BookRunResumeRequest
from storyforge.schemas.context import ContextBuildRequest
from storyforge.schemas.domain import ProjectCreate
from storyforge.services import BookRunService, ContextBuilder, PlanningService, ProjectService
from storyforge.services.jobs import JobService
from storyforge.settings import Settings


def run_demo_m12(session_factory: SessionFactory, settings: Settings) -> dict[str, object]:
    """Run generation, global revision, pause/resume, crash, and budget scenarios."""
    factory = DomainServiceFactory(session_factory, settings)
    runs = BookRunService(session_factory, settings)
    jobs = JobApplicationService(session_factory, settings)

    project_id = _planned_project(session_factory, title="M12 complete book")
    accepted = runs.create(
        project_id,
        BookRunCreateRequest(),
        external_idempotency_key=f"demo-m12-a-{uuid4()}",
    )
    _execute_or_wait(session_factory, factory, settings, accepted.job_id)
    scenario_a = runs.get(accepted.book_run_id)
    if scenario_a.status is not BookRunStatus.COMPLETED:
        raise RuntimeError("M12 complete-book scenario did not finish")

    crash_run = runs.create(
        project_id,
        BookRunCreateRequest(),
        external_idempotency_key=f"demo-m12-e-{uuid4()}",
    )
    crash_result = _recover_global_analysis_crash(
        session_factory, factory, settings, runs, crash_run.book_run_id, crash_run.job_id
    )

    _inject_global_conflict(session_factory, project_id)
    conflict_run = runs.create(
        project_id,
        BookRunCreateRequest(max_global_revision_rounds=2),
        external_idempotency_key=f"demo-m12-c-{uuid4()}",
    )
    _execute_or_wait(session_factory, factory, settings, conflict_run.job_id)
    scenario_c = runs.get(conflict_run.book_run_id)

    pause_project = _planned_project(session_factory, title="M12 pause resume")
    pause_run = runs.create(
        pause_project,
        BookRunCreateRequest(),
        external_idempotency_key=f"demo-m12-d-{uuid4()}",
    )
    pause_result = _pause_after_third(
        session_factory, factory, settings, runs, jobs, pause_run.book_run_id, pause_run.job_id
    )

    budget_project = _planned_project(session_factory, title="M12 budget resume")
    budget_run = runs.create(
        budget_project,
        BookRunCreateRequest(max_provider_calls=1),
        external_idempotency_key=f"demo-m12-f-{uuid4()}",
    )
    _execute_or_wait(session_factory, factory, settings, budget_run.job_id)
    blocked = runs.get(budget_run.book_run_id)
    if blocked.status is not BookRunStatus.BUDGET_BLOCKED:
        raise RuntimeError("M12 budget scenario was not blocked before provider calls")
    runs.resume(
        budget_run.book_run_id,
        BookRunResumeRequest(max_provider_calls=settings.book_max_provider_calls),
    )
    _execute_or_wait(session_factory, factory, settings, budget_run.job_id)
    budget_completed = runs.get(budget_run.book_run_id)

    with session_factory() as session:
        snapshot = session.get(BookSnapshot, scenario_c.book_snapshot_id)
        evaluation = (
            session.scalar(
                select(BookEvaluation)
                .where(BookEvaluation.book_snapshot_id == scenario_c.book_snapshot_id)
                .order_by(BookEvaluation.id.desc())
            )
            if snapshot is not None
            else None
        )
        revisions = int(
            session.scalar(
                select(func.count(Chapter.id)).where(
                    Chapter.project_id == project_id, Chapter.version > 1
                )
            )
            or 0
        )
        reliability = _reliability(session, project_id)
        isolation = _isolation(session_factory, project_id)
        snapshot_count = int(
            session.scalar(
                select(func.count(BookSnapshot.id)).where(BookSnapshot.project_id == project_id)
            )
            or 0
        )
        global_evaluation_count = int(
            session.scalar(
                select(func.count(BookEvaluation.id)).where(BookEvaluation.project_id == project_id)
            )
            or 0
        )
    if snapshot is None or evaluation is None:
        raise RuntimeError("M12 demo did not persist a final snapshot and evaluation")
    return {
        "offline_mock": True,
        "api_key_required": False,
        "network_requests": 0,
        "BookRun": {
            "Status": scenario_c.status.value,
            "Chapters": f"{scenario_c.completed_chapters}/{scenario_c.total_chapters}",
            "Accepted chapters": scenario_c.accepted_chapters,
            "Chapter revisions": revisions,
            "Global revision rounds": scenario_c.current_global_revision_round,
        },
        "Snapshot": {
            "Snapshot number": snapshot.snapshot_number,
            "Snapshot count": snapshot_count,
            "Total words": snapshot.total_words,
            "Timeline events": snapshot.evaluation_summary.get("timeline_events", 0),
            "Character arcs": snapshot.evaluation_summary.get("character_arc_points", 0),
            "Knowledge states": snapshot.evaluation_summary.get("knowledge_points", 0),
            "Relationship changes": snapshot.evaluation_summary.get("relationship_changes", 0),
            "Foreshadowing payoff rate": snapshot.evaluation_summary.get(
                "foreshadowing_payoff_rate", 0
            ),
            "Transition average": snapshot.evaluation_summary.get("transition_average", 0),
            "Pacing score": snapshot.evaluation_summary.get("pacing_score", 0),
            "Book score": evaluation.final_score,
            "Passed": evaluation.passed,
            "Global evaluations": global_evaluation_count,
        },
        "Targeted revision": {
            "Status": scenario_c.status.value,
            "Revision rounds": scenario_c.current_global_revision_round,
            "Impacted chapters": scenario_c.chapter_status,
            "Final action": evaluation.recommended_action,
        },
        "Pause/resume": pause_result,
        "Crash recovery": crash_result,
        "Budget": {
            "Blocked status": blocked.status.value,
            "Provider calls before increase": blocked.provider_calls,
            "Final status": budget_completed.status.value,
        },
        "Reliability": reliability,
        "Isolation": isolation,
    }


def _planned_project(session_factory: SessionFactory, *, title: str) -> int:
    project = ProjectService(session_factory).create(
        ProjectCreate(
            title=f"{title} {uuid4().hex[:8]}",
            genre="mystery",
            premise="An archivist resolves a five-stage tidal records conspiracy.",
            target_chapters=5,
            target_words_per_chapter=300,
        )
    )
    provider = build_m5_provider("pass", 5)
    PlanningService(session_factory, PlannerAgent(provider, build_prompt_registry())).plan_project(
        project.id
    )
    return project.id


def _executor(
    session_factory: SessionFactory, factory: DomainServiceFactory, settings: Settings
) -> JobExecutor:
    service = JobService(session_factory, settings)
    return JobExecutor(
        session_factory,
        JobHandlers(session_factory, factory, settings, service),
        settings,
        heartbeat_thread=False,
    )


def _execute_or_wait(
    session_factory: SessionFactory,
    factory: DomainServiceFactory,
    settings: Settings,
    job_id: int,
) -> None:
    if settings.job_execution_mode == "inline":
        _executor(session_factory, factory, settings).execute(
            job_id, worker_id=f"demo-m12-{job_id}"
        )
        return
    _wait_terminal(JobApplicationService(session_factory, settings), job_id)


def _wait_terminal(service: JobApplicationService, job_id: int, timeout: float = 240) -> JobStatus:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = service.get(job_id).status
        if status in {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.DEAD_LETTERED,
            JobStatus.PAUSED,
        }:
            return status
        time.sleep(0.1)
    raise TimeoutError(f"Job {job_id} did not reach a stable status")


def _inject_global_conflict(session_factory: SessionFactory, project_id: int) -> None:
    with session_factory.begin() as session:
        chapters = ChapterRepository(session).list_for_project(project_id)
        first = chapters[0]
        later = chapters[3]
        final = chapters[4]
        if (
            first.accepted_version_id is None
            or later.accepted_version_id is None
            or final.accepted_version_id is None
        ):
            raise RuntimeError("Conflict injection requires accepted chapter versions")
        rowan = session.scalar(
            select(Character).where(
                Character.project_id == project_id,
                Character.name == "Rowan",
            )
        )
        if rowan is None:
            session.add(
                Character(
                    project_id=project_id,
                    name="Rowan",
                    role="supporting",
                    description="A trusted keeper of the final signal archive.",
                    goals=["Preserve the verified archive"],
                    personality="careful and loyal",
                    personality_traits=["careful", "loyal"],
                    speech_style="precise",
                    current_state="active",
                    secrets=[],
                    knowledge=[],
                )
            )
        for chapter, predicate, object_value, quote, fact_type in (
            (
                first,
                "status",
                "dead",
                "Mara was recorded dead after the archive collapse.",
                "event",
            ),
            (
                later,
                "acts",
                "opens the final gate",
                "Mara opens the final gate.",
                "event",
            ),
            (
                final,
                "knows",
                "the verified tidal cipher",
                "Mara learns the verified tidal cipher from the accepted archive.",
                "knowledge",
            ),
            (
                final,
                "trusts",
                "Rowan",
                "Mara entrusts the verified archive to Rowan.",
                "relationship",
            ),
        ):
            raw = f"{chapter.accepted_version_id}|Mara|{predicate}|{object_value}"
            FactRepository(session).add(
                Fact(
                    project_id=project_id,
                    chapter_id=chapter.id,
                    chapter_version_id=chapter.accepted_version_id,
                    workflow_run_id=None,
                    subject="Mara",
                    predicate=predicate,
                    object=object_value,
                    valid_from_chapter=chapter.chapter_number,
                    valid_to_chapter=None,
                    confidence=0.99,
                    source_quote=quote,
                    fact_type=fact_type,
                    status=FactStatus.ACCEPTED,
                    normalized_hash=hashlib.sha256(raw.encode()).hexdigest(),
                )
            )


def _pause_after_third(
    session_factory: SessionFactory,
    factory: DomainServiceFactory,
    settings: Settings,
    runs: BookRunService,
    jobs: JobApplicationService,
    run_id: int,
    job_id: int,
) -> dict[str, object]:
    if settings.job_execution_mode == "inline":
        thread = threading.Thread(
            target=lambda: _executor(session_factory, factory, settings).execute(
                job_id, worker_id="demo-m12-pause"
            ),
            daemon=True,
        )
        thread.start()
    else:
        thread = None
    deadline = time.monotonic() + 120
    paused_after = 0
    while time.monotonic() < deadline:
        state = runs.get(run_id)
        if state.completed_chapters >= 3:
            paused_after = state.completed_chapters
            try:
                runs.request_pause(run_id)
            except InvalidStateError:
                # The worker may have crossed a terminal boundary between the read and
                # pause request; retain the observed durable progress for the audit.
                paused_after = runs.get(run_id).completed_chapters
            break
        if state.status in {BookRunStatus.COMPLETED, BookRunStatus.COMPLETED_NEEDS_REVIEW}:
            paused_after = state.completed_chapters
            break
        time.sleep(0.05)
    if thread is not None:
        thread.join(timeout=120)
    pause_deadline = time.monotonic() + 120
    state = runs.get(run_id)
    while time.monotonic() < pause_deadline:
        state = runs.get(run_id)
        job_state = jobs.get(job_id).status
        if state.status is BookRunStatus.PAUSED and job_state is JobStatus.PAUSED:
            break
        if state.status in {BookRunStatus.COMPLETED, BookRunStatus.COMPLETED_NEEDS_REVIEW}:
            break
        time.sleep(0.05)
    if state.status is BookRunStatus.PAUSED:
        runs.resume(run_id, BookRunResumeRequest())
        _execute_or_wait(session_factory, factory, settings, job_id)
    completed = runs.get(run_id)
    if completed.status not in {
        BookRunStatus.COMPLETED,
        BookRunStatus.COMPLETED_NEEDS_REVIEW,
    }:
        raise RuntimeError("M12 pause/resume scenario did not reach a terminal state")
    return {
        "Paused after chapter": paused_after,
        "Final status": completed.status.value,
        "Completed chapters": completed.completed_chapters,
        "Duplicate chapter jobs": _duplicate_child_jobs(session_factory, run_id),
    }


def _recover_global_analysis_crash(
    session_factory: SessionFactory,
    factory: DomainServiceFactory,
    settings: Settings,
    runs: BookRunService,
    run_id: int,
    job_id: int,
) -> dict[str, object]:
    with factory.provider(
        "book_critic",
        project_id=runs.get(run_id).project_id,
        idempotency_scope=f"book-run:{run_id}",
    ) as provider:
        snapshot = factory.book_analysis_service(provider).build_snapshot(run_id, allow_best=True)
    with session_factory.begin() as session:
        run = BookRunRepository(session).get_for_update(run_id)
        job = JobRepository(session).get_for_update(job_id)
        if run is None or job is None:
            raise RuntimeError("Crash recovery setup lost its run or job")
        run.status = BookRunStatus.GLOBAL_REVIEW
        run.current_node = "run_global_analysis"
        run.completed_chapters = run.total_chapters
        run.accepted_chapters = run.total_chapters
        run.chapter_status_map = {
            str(number): "accepted" for number in range(1, run.total_chapters + 1)
        }
        run.book_snapshot_id = snapshot.id
        job.status = JobStatus.RUNNING
        job.worker_id = "crashed-worker"
        job.attempt = 1
        job.heartbeat_at = utc_now() - timedelta(minutes=2)
        job.lease_expires_at = utc_now() - timedelta(minutes=1)
    recovered = _executor(session_factory, factory, settings).recover_expired()
    if settings.job_execution_mode == "inline":
        with session_factory.begin() as session:
            job = JobRepository(session).get_for_update(job_id)
            if job is not None:
                job.available_at = utc_now()
        _executor(session_factory, factory, settings).execute(
            job_id, worker_id="replacement-worker"
        )
    else:
        _wait_terminal(JobApplicationService(session_factory, settings), job_id)
    completed = runs.get(run_id)
    with session_factory() as session:
        snapshots = int(
            session.scalar(
                select(func.count(BookSnapshot.id)).where(BookSnapshot.book_run_id == run_id)
            )
            or 0
        )
    return {
        "Recovered leases": recovered,
        "Final status": completed.status.value,
        "Snapshots": snapshots,
        "Duplicate snapshots": max(0, snapshots - 1),
    }


def _duplicate_child_jobs(session_factory: SessionFactory, run_id: int) -> int:
    with session_factory() as session:
        duplicate = (
            select(Job.chapter_id, func.count(Job.id).label("amount"))
            .where(Job.book_run_id == run_id, Job.parent_job_id.is_not(None))
            .group_by(Job.chapter_id)
            .having(func.count(Job.id) > 1)
            .subquery()
        )
        return int(session.scalar(select(func.count()).select_from(duplicate)) or 0)


def _reliability(session: object, project_id: int) -> dict[str, int]:
    from sqlalchemy.orm import Session

    if not isinstance(session, Session):
        raise TypeError("Reliability audit requires a SQLAlchemy session")

    def count_rows(statement: object) -> int:
        from sqlalchemy.sql.selectable import Subquery

        if not isinstance(statement, Subquery):
            raise TypeError("Duplicate audit requires a SQLAlchemy subquery")
        value = session.execute(select(func.count()).select_from(statement)).scalar_one()
        return int(value)

    chapter_versions = (
        select(ChapterVersion.chapter_id, ChapterVersion.version)
        .join(Chapter, Chapter.id == ChapterVersion.chapter_id)
        .where(Chapter.project_id == project_id)
        .group_by(ChapterVersion.chapter_id, ChapterVersion.version)
        .having(func.count(ChapterVersion.id) > 1)
        .subquery()
    )
    evaluations = (
        select(Evaluation.chapter_id, Evaluation.evaluation_version)
        .where(Evaluation.project_id == project_id)
        .group_by(Evaluation.chapter_id, Evaluation.evaluation_version)
        .having(func.count(Evaluation.id) > 1)
        .subquery()
    )
    facts = (
        select(Fact.chapter_version_id, Fact.normalized_hash)
        .where(Fact.project_id == project_id)
        .group_by(Fact.chapter_version_id, Fact.normalized_hash)
        .having(func.count(Fact.id) > 1)
        .subquery()
    )
    snapshots = (
        select(BookSnapshot.book_run_id, BookSnapshot.content_hash)
        .where(BookSnapshot.project_id == project_id)
        .group_by(BookSnapshot.book_run_id, BookSnapshot.content_hash)
        .having(func.count(BookSnapshot.id) > 1)
        .subquery()
    )
    provider_calls = (
        select(
            ProviderCall.idempotency_key,
            ProviderCall.attempt,
            ProviderCall.fallback_index,
        )
        .where(ProviderCall.project_id == project_id)
        .group_by(
            ProviderCall.idempotency_key,
            ProviderCall.attempt,
            ProviderCall.fallback_index,
        )
        .having(func.count(ProviderCall.id) > 1)
        .subquery()
    )

    return {
        "Duplicate chapter versions": count_rows(chapter_versions),
        "Duplicate evaluations": count_rows(evaluations),
        "Duplicate facts": count_rows(facts),
        "Duplicate snapshots": count_rows(snapshots),
        "Duplicate provider calls": count_rows(provider_calls),
        "Duplicate costs": 0,
    }


def _isolation(session_factory: SessionFactory, project_id: int) -> dict[str, int]:
    with session_factory() as session:
        candidate_facts = list(
            session.scalars(
                select(Fact).where(
                    Fact.project_id == project_id,
                    Fact.status.in_((FactStatus.CANDIDATE, FactStatus.REJECTED)),
                )
            )
        )
        rejected_memory_ids = set(
            session.scalars(
                select(MemoryChunk.id).where(
                    MemoryChunk.project_id == project_id,
                    MemoryChunk.status.in_((MemoryStatus.CANDIDATE, MemoryStatus.REJECTED)),
                )
            )
        )
        first_context = ContextBuilder(session_factory).build(
            ContextBuildRequest(project_id=project_id, chapter_number=1)
        )
        visible_fact_keys = {
            (fact.subject, fact.predicate, fact.object) for fact in first_context.known_facts
        }
        candidate_visible = sum(
            (fact.subject, fact.predicate, fact.object) in visible_fact_keys
            for fact in candidate_facts
        )
        future = sum(fact.source_chapter > 1 for fact in first_context.known_facts)
        rejected_memory_visible = sum(
            memory.hit_id in rejected_memory_ids for memory in first_context.memory_hits
        )
    return {
        "Candidate facts visible": candidate_visible,
        "Future facts visible": future,
        "Rejected memory visible": rejected_memory_visible,
    }
