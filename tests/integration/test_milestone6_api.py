"""End-to-end verification of the stable Milestone 6 REST boundary."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from storyforge.api.app import create_app
from storyforge.api.dependencies import get_project_service
from storyforge.llm.exceptions import LLMConfigurationError, LLMTimeoutError
from storyforge.migrations import MIGRATION_HEAD
from storyforge.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    database = tmp_path / "m6-api.sqlite3"
    database_url = f"sqlite:///{database.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    settings = Settings(
        environment="test",
        database_url=database_url,
        llm_provider="mock",
        mock_workflow_scenario="improve",
        checkpoint_path=tmp_path / "m6-checkpoints.sqlite3",
        allow_debug_pause_nodes=True,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def _project_payload(title: str = "API Story") -> dict[str, object]:
    return {
        "title": title,
        "genre": "mystery",
        "premise": "An archivist investigates a sealed tidal records network.",
        "target_chapters": 3,
        "target_words_per_chapter": 300,
        "language": "en",
        "tone": "restrained",
        "audience": "adult",
        "additional_requirements": "Keep evidence auditable.",
    }


def _create_project(client: TestClient, title: str = "API Story") -> int:
    response = client.post("/api/v1/projects", json=_project_payload(title))
    assert response.status_code == 201
    assert response.headers["location"].endswith(f"/{response.json()['id']}")
    assert response.json()["status"] == "created"
    return int(response.json()["id"])


def _plan(client: TestClient, project_id: int) -> None:
    response = client.post(f"/api/v1/projects/{project_id}/plan", json={})
    assert response.status_code == 200
    assert len(response.json()["chapter_plans"]) == 3


def test_complete_api_path_is_typed_paginated_and_future_safe(
    api_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    request_id = "m6-e2e-request"
    health = api_client.get("/health")
    ready = api_client.get("/api/v1/ready", headers={"X-Request-ID": request_id})
    assert health.json() == {"status": "ok", "service": "storyforge", "version": "0.1.0"}
    assert ready.status_code == 200
    assert ready.headers["x-request-id"] == request_id
    assert ready.json()["migration_revision"] == MIGRATION_HEAD

    project_id = _create_project(api_client)
    listing = api_client.get("/api/v1/projects?page=1&page_size=1&sort=title&order=asc")
    assert listing.status_code == 200
    assert listing.json()["meta"] == {
        "page": 1,
        "page_size": 1,
        "total_items": 1,
        "total_pages": 1,
    }
    _plan(api_client, project_id)

    chapters = api_client.get(f"/api/v1/projects/{project_id}/chapters?page_size=2")
    assert chapters.status_code == 200
    assert chapters.json()["meta"]["total_items"] == 3
    assert all("content" not in item for item in chapters.json()["items"])
    context = api_client.get(f"/api/v1/projects/{project_id}/chapters/1/context")
    assert context.status_code == 200
    assert "author_secrets" not in context.json()
    assert context.json()["known_fact_count"] == 0

    with caplog.at_level(logging.INFO):
        workflow = api_client.post(
            f"/api/v1/projects/{project_id}/chapters/1/workflow",
            json={"max_revision_attempts": 2},
        )
    assert workflow.status_code == 201
    workflow_payload = workflow.json()
    assert workflow_payload["status"] == "completed"
    assert workflow_payload["accepted_version"] == 2
    assert workflow_payload["revision_attempt"] == 1
    assert "Before sunrise, Mara crossed" not in caplog.text

    chapter = api_client.get(f"/api/v1/projects/{project_id}/chapters/1")
    assert chapter.status_code == 200
    assert chapter.json()["content"] is None
    assert chapter.json()["accepted_version"]["version"] == 2
    chapter_with_content = api_client.get(
        f"/api/v1/projects/{project_id}/chapters/1?include_content=true"
    )
    assert chapter_with_content.status_code == 200
    assert chapter_with_content.json()["content"]

    versions = api_client.get(f"/api/v1/projects/{project_id}/chapters/1/versions")
    assert versions.status_code == 200
    assert versions.json()["meta"]["total_items"] == 2
    newest, oldest = versions.json()["items"]
    assert "content" not in newest
    version = api_client.get(f"/api/v1/projects/{project_id}/chapters/1/versions/{newest['id']}")
    assert version.json()["content"] is None
    diff = api_client.get(
        f"/api/v1/projects/{project_id}/chapters/1/versions/{newest['id']}/diff",
        params={"old_version_id": oldest["id"], "include_unified_diff": True},
    )
    assert diff.status_code == 200
    assert diff.json()["changed_line_count"] > 0

    evaluations = api_client.get(f"/api/v1/projects/{project_id}/chapters/1/evaluations")
    assert evaluations.status_code == 200
    assert evaluations.json()["meta"]["total_items"] == 2
    latest_evaluation = evaluations.json()["items"][0]
    detail = api_client.get(
        f"/api/v1/projects/{project_id}/chapters/1/evaluations/{latest_evaluation['id']}"
    )
    assert detail.status_code == 200
    assert detail.json()["mechanical_metrics"]
    assert detail.json()["critic_dimensions"]
    assert detail.json()["prompt_versions"]

    facts = api_client.get(f"/api/v1/projects/{project_id}/facts")
    assert facts.status_code == 200
    assert facts.json()["meta"]["total_items"] == 1
    assert {item["status"] for item in facts.json()["items"]} == {"accepted"}
    assert (
        api_client.get(f"/api/v1/projects/{project_id}/facts?status=candidate").status_code == 422
    )
    at_chapter_one = api_client.get(f"/api/v1/projects/{project_id}/facts?valid_at_chapter=1")
    assert at_chapter_one.json()["items"] == []

    conflicts = api_client.get(f"/api/v1/projects/{project_id}/conflicts?page_size=100")
    assert conflicts.status_code == 200
    assert conflicts.json()["meta"]["total_items"] >= 1
    events = api_client.get(
        f"/api/v1/workflow-runs/{workflow_payload['workflow_run_id']}/events?page_size=100"
    )
    assert events.status_code == 200
    assert events.json()["meta"]["total_items"] >= 10
    runs = api_client.get(f"/api/v1/projects/{project_id}/workflow-runs")
    assert runs.json()["items"][0]["status"] == "completed"

    openapi = api_client.get("/openapi.json")
    assert openapi.status_code == 200
    operations = [
        operation["operationId"]
        for path in openapi.json()["paths"].values()
        for operation in path.values()
    ]
    assert len(operations) == len(set(operations))
    assert len(openapi.json()["paths"]) == 26
    assert all(
        operation.get("description")
        for path in openapi.json()["paths"].values()
        for operation in path.values()
    )


def test_errors_conflict_transitions_and_workflow_concurrency_are_explicit(
    api_client: TestClient,
) -> None:
    missing = api_client.get("/api/v1/projects/999", headers={"X-Request-ID": "known-request"})
    assert missing.status_code == 404
    assert missing.json()["error"] == "resource_not_found"
    assert missing.json()["request_id"] == "known-request"
    invalid = api_client.post("/api/v1/projects", json={"title": ""})
    assert invalid.status_code == 422
    assert invalid.json()["details"]
    assert invalid.json()["request_id"]
    assert "traceback" not in invalid.text.casefold()

    project_id = _create_project(api_client, "Conflict transitions")
    provider_override = api_client.post(
        f"/api/v1/projects/{project_id}/plan",
        json={"provider": "openai-compatible"},
    )
    assert provider_override.status_code == 422
    _plan(api_client, project_id)
    paused = api_client.post(
        f"/api/v1/projects/{project_id}/chapters/1/workflow",
        json={"max_revision_attempts": 2, "pause_after_node": "evaluate_draft"},
    )
    assert paused.status_code == 201
    assert paused.json()["status"] == "paused"
    duplicate = api_client.post(f"/api/v1/projects/{project_id}/chapters/1/workflow", json={})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"] == "workflow_already_running"
    assert (
        api_client.post(
            f"/api/v1/projects/{project_id}/plan", json={"replace_existing": True}
        ).status_code
        == 409
    )
    resumed = api_client.post(f"/api/v1/workflow-runs/{paused.json()['workflow_run_id']}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] in {"completed", "completed_needs_review"}
    assert (
        api_client.post(
            f"/api/v1/workflow-runs/{paused.json()['workflow_run_id']}/resume"
        ).status_code
        == 409
    )
    assert (
        api_client.post(
            f"/api/v1/workflow-runs/{paused.json()['workflow_run_id']}/cancel"
        ).status_code
        == 409
    )

    conflicts = api_client.get(f"/api/v1/projects/{project_id}/conflicts?page_size=100")
    conflict_id = conflicts.json()["items"][0]["id"]
    resolved = api_client.patch(
        f"/api/v1/projects/{project_id}/conflicts/{conflict_id}",
        json={"status": "resolved", "resolution_note": "Reviewed in M6 test"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolved_at"] is not None
    invalid_transition = api_client.patch(
        f"/api/v1/projects/{project_id}/conflicts/{conflict_id}",
        json={"status": "false_positive"},
    )
    assert invalid_transition.status_code == 409
    reopened = api_client.patch(
        f"/api/v1/projects/{project_id}/conflicts/{conflict_id}",
        json={"status": "open"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["resolved_at"] is None

    restricted_settings = api_client.app.state.settings.model_copy(
        update={"allow_debug_pause_nodes": False}
    )
    with TestClient(create_app(restricted_settings)) as restricted_client:
        forbidden_pause = restricted_client.post(
            f"/api/v1/projects/{project_id}/chapters/2/workflow",
            json={"pause_after_node": "evaluate_draft"},
        )
    assert forbidden_pause.status_code == 422
    assert forbidden_pause.json()["error"] == "domain_validation"


def test_project_update_delete_and_request_limits(api_client: TestClient) -> None:
    project_id = _create_project(api_client, "Mutable project")
    updated = api_client.patch(f"/api/v1/projects/{project_id}", json={"title": "Renamed project"})
    assert updated.status_code == 200
    assert updated.json()["title"] == "Renamed project"
    deleted = api_client.delete(f"/api/v1/projects/{project_id}")
    assert deleted.status_code == 200

    planned_id = _create_project(api_client, "Protected project")
    _plan(api_client, planned_id)
    assert api_client.delete(f"/api/v1/projects/{planned_id}").status_code == 409
    assert (
        api_client.patch(
            f"/api/v1/projects/{planned_id}", json={"premise": "Changed after planning"}
        ).status_code
        == 409
    )
    assert api_client.get("/api/v1/projects?page=0").status_code == 422
    assert api_client.get("/api/v1/projects?page_size=101").status_code == 422
    oversized = api_client.post(
        "/api/v1/projects",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": "1048577"},
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"] == "request_too_large"


class _FailingProjectService:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def create(self, payload: object) -> object:
        del payload
        raise self._error


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (LLMConfigurationError("must not leak sk-provider-secret"), 503, "provider_configuration"),
        (
            LLMTimeoutError("must not leak sk-timeout-secret", attempts=1),
            504,
            "provider_timeout",
        ),
    ],
)
def test_dependency_overrides_and_provider_errors_are_sanitized(
    api_client: TestClient,
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    api_client.app.dependency_overrides[get_project_service] = lambda: _FailingProjectService(error)
    try:
        response = api_client.post("/api/v1/projects", json=_project_payload())
    finally:
        api_client.app.dependency_overrides.clear()
    assert response.status_code == status_code
    assert response.json()["error"] == code
    assert "sk-" not in response.text


def test_unexpected_errors_and_readiness_failure_do_not_leak_details(
    api_client: TestClient,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = api_client.app.state.settings
    application = create_app(settings)
    application.dependency_overrides[get_project_service] = lambda: _FailingProjectService(
        RuntimeError("C:/private/path sk-internal-secret full chapter body")
    )
    with (
        caplog.at_level(logging.ERROR),
        TestClient(application, raise_server_exceptions=False) as client,
    ):
        response = client.post("/api/v1/projects", json=_project_payload())
    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"
    assert "sk-internal-secret" not in response.text
    assert "sk-internal-secret" not in caplog.text
    assert "full chapter body" not in caplog.text

    unavailable = Settings(
        environment="test",
        database_url=f"sqlite:///{(tmp_path / 'missing' / 'ready.sqlite3').as_posix()}",
        llm_provider="mock",
        checkpoint_path=tmp_path / "unavailable-checkpoints.sqlite3",
    )
    with TestClient(create_app(unavailable), raise_server_exceptions=False) as client:
        not_ready = client.get("/api/v1/ready")
    assert not_ready.status_code == 503
    assert not_ready.json()["error"] == "database_unavailable"
    assert str(tmp_path) not in not_ready.text
