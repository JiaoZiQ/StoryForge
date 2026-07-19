"""Milestone 12 API, CLI, persistence, idempotency, and recovery integration."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from storyforge.api.app import create_app
from storyforge.application import DomainServiceFactory
from storyforge.cli.app import main
from storyforge.database import create_database_engine, create_session_factory
from storyforge.enums import BookRunStatus, JobStatus
from storyforge.jobs.handlers import JobHandlers
from storyforge.jobs.worker import JobExecutor
from storyforge.models import BookRun, Job, JobEvent, OutboxMessage
from storyforge.services.jobs import JobService
from storyforge.settings import Settings

ROOT = Path(__file__).resolve().parents[2]


def _has_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_has_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_has_key(item, key) for item in value)
    return False


@pytest.fixture
def m12_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Settings]]:
    database = tmp_path / "m12-api.sqlite3"
    database_url = f"sqlite:///{database.as_posix()}"
    monkeypatch.setenv("STORYFORGE_DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("STORYFORGE_ENVIRONMENT", "test")
    monkeypatch.setenv("STORYFORGE_JOB_EXECUTION_MODE", "inline")
    monkeypatch.setenv("STORYFORGE_REDIS_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    settings = Settings(
        environment="test",
        database_url=database_url,
        llm_provider="mock",
        job_execution_mode="inline",
        book_global_check_interval=2,
        checkpoint_path=tmp_path / "m12-checkpoints.sqlite3",
    )
    with TestClient(create_app(settings)) as client:
        yield client, settings


def _create_planned_project(client: TestClient, *, chapters: int = 2) -> int:
    response = client.post(
        "/api/v1/projects",
        json={
            "title": "Whole-book API",
            "genre": "mystery",
            "premise": "An archivist repairs a tidal record conspiracy.",
            "target_chapters": chapters,
            "target_words_per_chapter": 300,
        },
    )
    assert response.status_code == 201
    project_id = int(response.json()["id"])
    planned = client.post(f"/api/v1/projects/{project_id}/plan", json={})
    assert planned.status_code == 200
    assert len(planned.json()["chapter_plans"]) == chapters
    return project_id


def _execute_job(settings: Settings, job_id: int) -> None:
    engine = create_database_engine(settings.database_url)
    sessions = create_session_factory(engine)
    factory = DomainServiceFactory(sessions, settings)
    executor = JobExecutor(
        sessions,
        JobHandlers(sessions, factory, settings, JobService(sessions, settings)),
        settings,
        heartbeat_thread=False,
    )
    try:
        assert executor.execute(job_id, worker_id="m12-api-worker")
    finally:
        engine.dispose()


def test_book_api_admission_is_202_transactional_idempotent_and_content_free(
    m12_runtime: tuple[TestClient, Settings],
) -> None:
    client, settings = m12_runtime
    project_id = _create_planned_project(client)
    headers = {"Idempotency-Key": "book-api-stable-key"}
    first = client.post(f"/api/v1/projects/{project_id}/book-runs", json={}, headers=headers)
    replay = client.post(f"/api/v1/projects/{project_id}/book-runs", json={}, headers=headers)

    assert first.status_code == 202
    assert replay.status_code == 202
    assert replay.json()["reused"] is True
    assert first.json()["book_run_id"] == replay.json()["book_run_id"]
    run_id = int(first.json()["book_run_id"])
    job_id = int(first.json()["job_id"])

    engine = create_database_engine(settings.database_url)
    sessions = create_session_factory(engine)
    try:
        with sessions() as session:
            assert session.scalar(select(func.count(BookRun.id))) == 1
            assert session.scalar(select(func.count(Job.id)).where(Job.id == job_id)) == 1
            assert (
                session.scalar(
                    select(func.count(OutboxMessage.id)).where(
                        OutboxMessage.aggregate_type == "job",
                        OutboxMessage.aggregate_id == job_id,
                    )
                )
                == 1
            )
    finally:
        engine.dispose()

    conflicting = client.post(
        f"/api/v1/projects/{project_id}/book-runs",
        json={},
        headers={"Idempotency-Key": "another-key"},
    )
    assert conflicting.status_code == 202
    assert conflicting.json()["reused"] is True
    assert conflicting.json()["book_run_id"] == run_id

    _execute_job(settings, job_id)
    status_response = client.get(f"/api/v1/book-runs/{run_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] in {"completed", "completed_needs_review"}
    assert status_response.json()["completed_chapters"] == 2
    periodic = status_response.json()["periodic_checks"]
    assert periodic[0]["through_chapter"] == 2
    assert periodic[0]["critical_conflicts"] == 0

    snapshots = client.get(f"/api/v1/projects/{project_id}/book-snapshots")
    assert snapshots.status_code == 200
    snapshot = snapshots.json()["items"][0]
    assert not _has_key(snapshot, "content")
    snapshot_id = int(snapshot["id"])
    for suffix in (
        "evaluation",
        "timeline",
        "character-arcs",
        "relationships",
        "foreshadowing",
        "pacing",
        "transitions",
    ):
        response = client.get(f"/api/v1/book-snapshots/{snapshot_id}/{suffix}")
        assert response.status_code == 200, suffix
        assert not _has_key(response.json(), "content")

    events = client.get(f"/api/v1/book-runs/{run_id}/events?page_size=500")
    assert events.status_code == 200
    assert events.json()["total_items"] > 0
    assert not _has_key(events.json(), "content")

    completed_pause = client.post(f"/api/v1/book-runs/{run_id}/pause")
    completed_resume = client.post(f"/api/v1/book-runs/{run_id}/resume", json={})
    completed_cancel = client.post(f"/api/v1/book-runs/{run_id}/cancel")
    assert {
        completed_pause.status_code,
        completed_resume.status_code,
        completed_cancel.status_code,
    } == {409}

    engine = create_database_engine(settings.database_url)
    sessions = create_session_factory(engine)
    try:
        with sessions() as session:
            sequences = list(
                session.scalars(
                    select(JobEvent.sequence)
                    .where(JobEvent.job_id == job_id)
                    .order_by(JobEvent.sequence)
                )
            )
            assert sequences == list(range(1, len(sequences) + 1))
            assert session.get(Job, job_id).status is JobStatus.SUCCEEDED
    finally:
        engine.dispose()


def test_openapi_book_operation_ids_are_unique(m12_runtime: tuple[TestClient, Settings]) -> None:
    client, _ = m12_runtime
    schema = client.get("/openapi.json").json()
    operation_ids = [
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))
    assert "create_book_run" in operation_ids


def test_demo_m12_cli_is_parseable_offline_and_reports_reliability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "m12-demo.sqlite3"
    database_url = f"sqlite:///{database.as_posix()}"
    monkeypatch.setenv("STORYFORGE_DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("STORYFORGE_ENVIRONMENT", "test")
    monkeypatch.setenv("STORYFORGE_JOB_EXECUTION_MODE", "inline")
    monkeypatch.setenv("STORYFORGE_REDIS_ENABLED", "false")
    monkeypatch.setenv("STORYFORGE_CHECKPOINT_PATH", str(tmp_path / "checkpoints.sqlite3"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")

    assert main(["demo-m12", "--output", "json"]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["offline_mock"] is True
    assert output["network_requests"] == 0
    assert output["BookRun"]["Status"] == BookRunStatus.COMPLETED.value
    assert output["Snapshot"]["Passed"] is True
    assert output["Snapshot"]["Knowledge states"] > 0
    assert output["Snapshot"]["Relationship changes"] > 0
    assert output["Pause/resume"]["Final status"] == BookRunStatus.COMPLETED.value
    assert output["Crash recovery"]["Final status"] == BookRunStatus.COMPLETED.value
    assert output["Budget"]["Provider calls before increase"] == 0
    assert all(value == 0 for value in output["Reliability"].values())
    assert all(value == 0 for value in output["Isolation"].values())
