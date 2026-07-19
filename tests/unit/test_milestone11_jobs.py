"""Milestone 11 durable job, outbox, worker, and API regression tests."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from storyforge.api.app import create_app
from storyforge.application import DomainServiceFactory, JobApplicationService
from storyforge.cli.app import main as cli_main
from storyforge.database import create_database_engine, create_session_factory
from storyforge.enums import ChapterStatus, JobStatus, JobType, WorkerStatus, WorkflowRunStatus
from storyforge.exceptions import DomainValidationError, InvalidStateError, QueueBackpressureError
from storyforge.jobs.broker import InMemoryJobBroker
from storyforge.jobs.dispatcher import OutboxDispatcher
from storyforge.jobs.handlers import JobHandlers
from storyforge.jobs.transitions import transition_job
from storyforge.jobs.worker import JobExecutor
from storyforge.models import Base, Chapter, Job, JobEvent, OutboxMessage, WorkflowRun
from storyforge.models.base import utc_now
from storyforge.repositories import JobRepository, WorkerRepository
from storyforge.schemas.domain import ProjectCreate
from storyforge.schemas.jobs import JobCreateRequest
from storyforge.services import ProjectService
from storyforge.services.jobs import JobService
from storyforge.settings import Settings


def _runtime(db_engine):  # type: ignore[no-untyped-def]
    sessions = create_session_factory(db_engine)
    settings = Settings(database_url=str(db_engine.url), job_execution_mode="inline")
    project = ProjectService(sessions).create(
        ProjectCreate(
            title="Async tests",
            genre="sf",
            premise="Reliable work",
            target_chapters=3,
            target_words_per_chapter=1000,
        )
    )
    return sessions, settings, project


def _request(project_id: int, *, key: str = "same") -> JobCreateRequest:
    return JobCreateRequest(
        job_type=JobType.RUN_RETRIEVAL_WARMUP,
        project_id=project_id,
        operation="test",
        payload={"query": "test", "current_chapter": 1, "top_k": 3},
        idempotency_key=key,
    )


def test_job_and_outbox_are_atomic_and_idempotent(db_engine) -> None:  # type: ignore[no-untyped-def]
    sessions, settings, project = _runtime(db_engine)
    service = JobApplicationService(sessions, settings)
    first = service.create(_request(project.id))
    second = service.create(_request(project.id))
    assert first.job_id == second.job_id
    assert second.reused is True
    with sessions() as session:
        assert session.scalar(select(func.count(Job.id))) == 1
        assert session.scalar(select(func.count(OutboxMessage.id))) == 1
        assert session.scalar(select(func.count(JobEvent.id))) == 1


def test_payload_rejects_secrets_and_content(db_engine) -> None:  # type: ignore[no-untyped-def]
    sessions, settings, project = _runtime(db_engine)
    service = JobService(sessions, settings)
    with pytest.raises(DomainValidationError):
        service.create(
            job_type=JobType.GENERATE_PLAN,
            project_id=project.id,
            chapter_id=None,
            workflow_run_id=None,
            payload={"api_key": "secret"},
            operation="bad",
        )
    with pytest.raises(DomainValidationError):
        service.create(
            job_type=JobType.GENERATE_PLAN,
            project_id=project.id,
            chapter_id=None,
            workflow_run_id=None,
            payload={"content": "chapter"},
            operation="bad",
        )


def test_compose_workers_share_durable_workflow_checkpoints() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    expected = "storyforge_checkpoint_data:/tmp/storyforge"
    assert expected in compose["services"]["api"]["volumes"]
    assert expected in compose["services"]["worker"]["volumes"]
    assert "storyforge_checkpoint_data" in compose["volumes"]


def test_outbox_dispatches_only_job_id_and_execution_succeeds(db_engine) -> None:  # type: ignore[no-untyped-def]
    sessions, settings, project = _runtime(db_engine)
    service = JobApplicationService(sessions, settings)
    accepted = service.create(_request(project.id))
    broker = InMemoryJobBroker()
    assert OutboxDispatcher(sessions, broker, settings, dispatcher_id="test").dispatch_once() == 1
    assert broker.messages == [(accepted.job_id, "storyforge.indexing")]
    assert broker.timeouts == [600]
    factory = DomainServiceFactory(sessions, settings)
    executor = JobExecutor(
        sessions,
        JobHandlers(sessions, factory, settings, JobService(sessions, settings)),
        settings,
        heartbeat_thread=False,
    )
    assert executor.execute(accepted.job_id, worker_id="worker-1") is True
    result = service.get(accepted.job_id)
    assert result.status is JobStatus.SUCCEEDED
    assert result.progress == 100
    assert service.events(accepted.job_id, page=1, page_size=100).total_items >= 5
    assert executor.execute(accepted.job_id, worker_id="worker-1") is False


def test_cancel_before_dispatch_is_terminal(db_engine) -> None:  # type: ignore[no-untyped-def]
    sessions, settings, project = _runtime(db_engine)
    service = JobApplicationService(sessions, settings)
    accepted = service.create(_request(project.id))
    assert service.cancel(accepted.job_id).status is JobStatus.CANCELLED
    with pytest.raises(InvalidStateError):
        service.resume(accepted.job_id)


def test_cancel_paused_job_cancels_linked_workflow_atomically(db_engine) -> None:  # type: ignore[no-untyped-def]
    sessions, settings, project = _runtime(db_engine)
    service = JobApplicationService(sessions, settings)
    accepted = service.create(_request(project.id, key="cancel-linked"))
    with sessions.begin() as session:
        chapter = Chapter(
            project_id=project.id,
            chapter_number=1,
            title="Cancel",
            outline="Stop before acceptance",
            status=ChapterStatus.WORKFLOW_RUNNING,
        )
        session.add(chapter)
        session.flush()
        workflow = WorkflowRun(
            project_id=project.id,
            chapter_id=chapter.id,
            current_node="decide_after_comparison",
            status=WorkflowRunStatus.PAUSED,
            operation="generate",
            thread_id="cancel-paused-workflow",
        )
        session.add(workflow)
        session.flush()
        job = session.get(Job, accepted.job_id)
        assert job is not None
        job.status = JobStatus.PAUSED
        job.started_at = utc_now()
        job.workflow_run_id = workflow.id
        workflow_id = workflow.id
        chapter_id = chapter.id

    assert service.cancel(accepted.job_id).status is JobStatus.CANCELLED
    with sessions() as session:
        workflow = session.get(WorkflowRun, workflow_id)
        chapter = session.get(Chapter, chapter_id)
        assert workflow is not None and workflow.status is WorkflowRunStatus.CANCELLED
        assert chapter is not None and chapter.status is ChapterStatus.WORKFLOW_FAILED


def test_pause_and_resume_reuses_same_job(db_engine) -> None:  # type: ignore[no-untyped-def]
    sessions, settings, project = _runtime(db_engine)
    service = JobApplicationService(sessions, settings)
    accepted = service.create(_request(project.id))
    assert service.pause(accepted.job_id).status is JobStatus.PAUSED
    assert service.resume(accepted.job_id).status is JobStatus.OUTBOX_PENDING
    with sessions() as session:
        assert session.scalar(select(func.count(Job.id))) == 1
        assert session.scalar(select(func.count(OutboxMessage.id))) == 2


def test_expired_lease_is_recovered_without_duplicate_job(db_engine) -> None:  # type: ignore[no-untyped-def]
    sessions, settings, project = _runtime(db_engine)
    with sessions.begin() as session:
        chapter = Chapter(
            project_id=project.id,
            chapter_number=1,
            title="Recovery",
            outline="Checkpoint recovery",
        )
        session.add(chapter)
        session.flush()
        workflow = WorkflowRun(
            project_id=project.id,
            chapter_id=chapter.id,
            current_node="evaluate_draft",
            status=WorkflowRunStatus.RUNNING,
            operation="generate",
            thread_id="worker-crash-recovery",
        )
        session.add(workflow)
        session.flush()
        workflow_run_id = workflow.id
    service = JobApplicationService(sessions, settings)
    accepted = service.create(_request(project.id))
    broker = InMemoryJobBroker()
    OutboxDispatcher(sessions, broker, settings, dispatcher_id="test").dispatch_once()
    with sessions.begin() as session:
        job = JobRepository(session).get(accepted.job_id)
        assert job is not None
        job.status = JobStatus.RUNNING
        job.worker_id = "dead-worker"
        job.attempt = 1
        job.lease_expires_at = utc_now()
        job.workflow_run_id = workflow_run_id
    factory = DomainServiceFactory(sessions, settings)
    executor = JobExecutor(
        sessions,
        JobHandlers(sessions, factory, settings, JobService(sessions, settings)),
        settings,
        heartbeat_thread=False,
    )
    assert executor.recover_expired() == 1
    assert service.get(accepted.job_id).status is JobStatus.RETRY_SCHEDULED
    with sessions() as session:
        assert session.scalar(select(func.count(Job.id))) == 1
        recovered_workflow = session.get(WorkflowRun, workflow_run_id)
        assert recovered_workflow is not None
        assert recovered_workflow.status is WorkflowRunStatus.PAUSED


def test_redis_flush_reopens_published_outbox_without_duplicate_job(db_engine) -> None:  # type: ignore[no-untyped-def]
    sessions, settings, project = _runtime(db_engine)
    accepted = JobApplicationService(sessions, settings).create(_request(project.id))
    broker = InMemoryJobBroker()
    now = utc_now()
    clock = [now]
    dispatcher = OutboxDispatcher(
        sessions,
        broker,
        settings,
        dispatcher_id="redis-recovery",
        clock=lambda: clock[0],
    )
    assert dispatcher.dispatch_once() == 1
    clock[0] = now + timedelta(seconds=settings.job_lease_seconds + 1)
    assert dispatcher.recover_stranded() == 1
    assert dispatcher.dispatch_once() == 1
    assert broker.messages == [
        (accepted.job_id, "storyforge.indexing"),
        (accepted.job_id, "storyforge.indexing"),
    ]
    with sessions() as session:
        assert session.scalar(select(func.count(Job.id))) == 1
        assert session.scalar(select(func.count(OutboxMessage.id))) == 1


def test_dispatcher_applies_bounded_priority_order(db_engine) -> None:  # type: ignore[no-untyped-def]
    sessions, settings, project = _runtime(db_engine)
    service = JobApplicationService(sessions, settings)
    low = _request(project.id, key="low").model_copy(update={"priority": 1})
    high = _request(project.id, key="high").model_copy(update={"priority": 8})
    low_id = service.create(low).job_id
    high_id = service.create(high).job_id
    broker = InMemoryJobBroker()
    assert (
        OutboxDispatcher(sessions, broker, settings, dispatcher_id="priority").dispatch_once() == 2
    )
    assert [message[0] for message in broker.messages] == [high_id, low_id]


def test_outbox_publish_failure_is_bounded_and_dead_lettered(db_engine) -> None:  # type: ignore[no-untyped-def]
    class FailingBroker:
        def enqueue(
            self, job_id: int, queue_name: str, *, timeout_seconds: int | None = None
        ) -> str:
            raise RuntimeError("broker unavailable")

        def ping(self) -> bool:
            return False

    sessions, settings, project = _runtime(db_engine)
    accepted = JobApplicationService(sessions, settings).create(_request(project.id))
    clock = [utc_now()]
    dispatcher = OutboxDispatcher(
        sessions,
        FailingBroker(),
        settings,
        dispatcher_id="failure",
        clock=lambda: clock[0],
    )
    for _ in range(settings.job_max_attempts):
        assert dispatcher.dispatch_once() == 0
        clock[0] += timedelta(minutes=10)
    assert (
        JobApplicationService(sessions, settings).get(accepted.job_id).status
        is JobStatus.DEAD_LETTERED
    )


def test_global_and_project_backpressure_reject_before_extra_outbox(db_engine) -> None:  # type: ignore[no-untyped-def]
    sessions, _, project = _runtime(db_engine)
    settings = Settings(
        database_url=str(db_engine.url),
        job_execution_mode="inline",
        queue_pending_soft_limit=1,
        queue_pending_hard_limit=1,
        project_pending_limit=1,
    )
    service = JobApplicationService(sessions, settings)
    service.create(_request(project.id, key="first"))
    with pytest.raises(QueueBackpressureError):
        service.create(_request(project.id, key="second"))
    with sessions() as session:
        assert session.scalar(select(func.count(Job.id))) == 1
        assert session.scalar(select(func.count(OutboxMessage.id))) == 1
    project_two = ProjectService(sessions).create(
        ProjectCreate(
            title="Project pressure",
            genre="sf",
            premise="Fair capacity",
            target_chapters=2,
            target_words_per_chapter=1000,
        )
    )
    project_limited = JobApplicationService(
        sessions,
        settings.model_copy(update={"queue_pending_hard_limit": 100, "project_pending_limit": 1}),
    )
    project_limited.create(_request(project_two.id, key="project-first"))
    with pytest.raises(QueueBackpressureError):
        project_limited.create(_request(project_two.id, key="project-second"))


def test_only_one_active_job_is_allowed_per_chapter(db_engine) -> None:  # type: ignore[no-untyped-def]
    sessions, settings, project = _runtime(db_engine)
    with sessions.begin() as session:
        session.add(
            Chapter(
                project_id=project.id,
                chapter_number=1,
                title="One",
                outline="Outline",
            )
        )
    service = JobApplicationService(sessions, settings)
    first = JobCreateRequest(
        job_type=JobType.GENERATE_CHAPTER,
        project_id=project.id,
        chapter_number=1,
        operation="generate",
        idempotency_key="chapter-first",
    )
    service.create(first)
    with pytest.raises(InvalidStateError):
        service.create(first.model_copy(update={"idempotency_key": "chapter-second"}))


def test_state_machine_rejects_illegal_terminal_transition() -> None:
    job = Job(
        job_type=JobType.GENERATE_PLAN,
        queue_name="q",
        status=JobStatus.SUCCEEDED,
        priority=5,
        idempotency_key="x",
        payload={},
        result={},
        max_attempts=3,
        correlation_id="c",
    )
    with pytest.raises(InvalidStateError):
        transition_job(job, JobStatus.RUNNING)


def test_job_api_is_accepted_filterable_and_content_free(tmp_path: Path) -> None:
    database = tmp_path / "api.sqlite3"
    url = f"sqlite:///{database.as_posix()}"
    engine = create_database_engine(url)
    Base.metadata.create_all(engine)
    sessions = create_session_factory(engine)
    project = ProjectService(sessions).create(
        ProjectCreate(
            title="API",
            genre="sf",
            premise="queue",
            target_chapters=2,
            target_words_per_chapter=1000,
        )
    )
    with sessions.begin() as session:
        session.add(
            Chapter(
                project_id=project.id,
                chapter_number=1,
                title="API chapter",
                outline="Outline",
            )
        )
    try:
        with TestClient(
            create_app(Settings(database_url=url, job_execution_mode="inline"))
        ) as client:
            response = client.post(
                "/api/v1/jobs",
                json={
                    "job_type": "run_retrieval_warmup",
                    "project_id": project.id,
                    "operation": "api",
                    "payload": {"query": "x", "current_chapter": 1},
                },
            )
            assert response.status_code == 202
            job_id = response.json()["job_id"]
            detail = client.get(f"/api/v1/jobs/{job_id}")
            assert detail.status_code == 200
            rendered = detail.text.casefold()
            assert "payload" not in rendered
            assert "api_key" not in rendered
            listing = client.get("/api/v1/jobs?status=outbox_pending")
            assert listing.json()["total_items"] == 1
            assert client.post(f"/api/v1/jobs/{job_id}/pause").json()["status"] == "paused"
            assert client.post(f"/api/v1/jobs/{job_id}/resume").json()["status"] == "outbox_pending"
            assert client.post(f"/api/v1/jobs/{job_id}/cancel").json()["status"] == "cancelled"
            events = client.get(f"/api/v1/jobs/{job_id}/events").json()
            assert events["total_items"] >= 5
            first_event_id = events["items"][0]["id"]
            with client.stream(
                "GET",
                f"/api/v1/jobs/{job_id}/events/stream",
                headers={"Last-Event-ID": str(first_event_id)},
            ) as streamed:
                body = streamed.read().decode()
            assert streamed.status_code == 200
            assert "event: job_cancelled" in body
            health = client.get("/api/v1/queue/health").json()
            assert health["broker_reachable"] is True
            assert client.get("/api/v1/workers").status_code == 200
            assert client.get("/api/v1/workers/health").status_code == 200

            plan_job = client.post(
                f"/api/v1/projects/{project.id}/plan/jobs",
                json={"replace_existing": False},
                headers={"Idempotency-Key": "plan-api-key"},
            )
            assert plan_job.status_code == 202
            assert plan_job.json()["reused"] is False
            repeated = client.post(
                f"/api/v1/projects/{project.id}/plan/jobs",
                json={"replace_existing": False},
                headers={"Idempotency-Key": "plan-api-key"},
            )
            assert repeated.json()["job_id"] == plan_job.json()["job_id"]
            assert repeated.json()["reused"] is True
            generation = client.post(
                f"/api/v1/projects/{project.id}/chapters/1/generation-jobs",
                json={"regenerate": False, "max_context_chars": 24000},
            )
            assert generation.status_code == 202
            filtered = client.get(f"/api/v1/jobs?project_id={project.id}&chapter_number=1").json()
            assert [item["chapter_number"] for item in filtered["items"]] == [1]
            doomed = client.post(
                "/api/v1/jobs",
                json={
                    "job_type": "run_retrieval_warmup",
                    "project_id": project.id,
                    "operation": "doomed",
                    "payload": {"query": "x", "current_chapter": 1},
                },
            ).json()["job_id"]
            with sessions.begin() as session:
                row = JobRepository(session).get(doomed)
                assert row is not None
                transition_job(row, JobStatus.FAILED)
                transition_job(row, JobStatus.DEAD_LETTERED)
            dead = client.get("/api/v1/dead-letter-jobs").json()
            assert [item["id"] for item in dead["items"]] == [doomed]
            assert (
                client.post(f"/api/v1/dead-letter-jobs/{doomed}/discard").json()["result"][
                    "discarded"
                ]
                is True
            )
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_job_cli_json_and_worker_status_are_parseable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url = f"sqlite:///{(tmp_path / 'cli.sqlite3').as_posix()}"
    engine = create_database_engine(url)
    Base.metadata.create_all(engine)
    sessions = create_session_factory(engine)
    project = ProjectService(sessions).create(
        ProjectCreate(
            title="CLI",
            genre="sf",
            premise="queue",
            target_chapters=2,
            target_words_per_chapter=1000,
        )
    )
    monkeypatch.setenv("STORYFORGE_DATABASE_URL", url)
    monkeypatch.setenv("STORYFORGE_JOB_EXECUTION_MODE", "inline")
    try:
        assert (
            cli_main(
                [
                    "job",
                    "submit",
                    "--type",
                    "run_retrieval_warmup",
                    "--project-id",
                    str(project.id),
                    "--payload-json",
                    '{"query":"safe","current_chapter":1}',
                    "--output",
                    "json",
                ]
            )
            == 0
        )
        accepted = json.loads(capsys.readouterr().out)
        assert accepted["job_id"] > 0
        assert cli_main(["worker", "status", "--output", "json"]) == 0
        health = json.loads(capsys.readouterr().out)
        assert health["mode"] == "inline"
    finally:
        engine.dispose()


def test_worker_keepalive_preserves_busy_state_and_stale_workers_are_offline(db_engine) -> None:  # type: ignore[no-untyped-def]
    sessions, settings, project = _runtime(db_engine)
    job_id = JobApplicationService(sessions, settings).create(_request(project.id)).job_id
    first = utc_now()
    second = first + timedelta(seconds=1)
    with sessions.begin() as session:
        repository = WorkerRepository(session)
        repository.heartbeat(
            worker_id="worker-1",
            queue_name="all",
            status=WorkerStatus.BUSY,
            current_job_id=job_id,
            version="test",
            now=first,
        )
        repository.keepalive(
            worker_id="worker-1",
            queue_name="all",
            version="test",
            now=second,
        )
        worker = repository.get_by_worker_id("worker-1")
        assert worker is not None
        assert worker.status is WorkerStatus.BUSY
        assert worker.current_job_id == job_id
        worker.last_heartbeat_at = utc_now() - timedelta(seconds=120)

    health = JobApplicationService(sessions, settings).health(broker_reachable=True)
    assert health.workers[0].status is WorkerStatus.OFFLINE
