"""Milestone 10 provider, usage, budget, and project policy HTTP integration."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from storyforge.api.app import create_app
from storyforge.models import ProviderCall, WorkflowRun
from storyforge.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def governance_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    database = tmp_path / "m10-api.sqlite3"
    database_url = f"sqlite:///{database.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    settings = Settings(
        environment="test",
        database_url=database_url,
        llm_provider="mock",
        mock_workflow_scenario="pass",
        checkpoint_path=tmp_path / "m10-checkpoints.sqlite3",
        allow_debug_pause_nodes=True,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def _create_project(client: TestClient) -> int:
    response = client.post(
        "/api/v1/projects",
        json={
            "title": "Governed Story",
            "genre": "mystery",
            "premise": "A minimal provider governance integration test.",
            "target_chapters": 3,
            "target_words_per_chapter": 300,
            "language": "en",
        },
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def test_provider_budget_usage_and_settings_endpoints_are_safe(
    governance_client: TestClient,
) -> None:
    providers = governance_client.get("/api/v1/providers")
    assert providers.status_code == 200
    assert len(providers.json()) == 3
    assert all("api_key" not in item and "base_url" not in item for item in providers.json())
    health = governance_client.get("/api/v1/providers/health")
    assert health.status_code == 200
    assert {item["circuit_status"] for item in health.json()} == {"closed"}
    profiles = governance_client.get("/api/v1/system/model-profiles")
    assert [item["name"] for item in profiles.json()] == [
        "offline",
        "economy",
        "balanced",
        "quality",
    ]

    project_id = _create_project(governance_client)
    settings = governance_client.get(f"/api/v1/projects/{project_id}/model-settings")
    assert settings.json() == {
        "project_id": project_id,
        "model_profile": "offline",
        "privacy_policy": "offline",
    }
    profile = governance_client.patch(
        f"/api/v1/projects/{project_id}/model-profile",
        json={"model_profile": "balanced"},
    )
    assert profile.status_code == 200
    privacy = governance_client.patch(
        f"/api/v1/projects/{project_id}/privacy-policy",
        json={"privacy_policy": "strict"},
    )
    assert privacy.status_code == 200
    assert (
        governance_client.patch(
            f"/api/v1/projects/{project_id}/model-profile",
            json={"model_profile": "unregistered-model"},
        ).status_code
        == 422
    )

    budget = governance_client.put(
        f"/api/v1/projects/{project_id}/budget",
        json={
            "currency": "USD",
            "soft_limit": "1.00000001",
            "hard_limit": "2.00000002",
            "period": "lifetime",
            "enabled": True,
        },
    )
    assert budget.status_code == 200
    assert budget.json()["hard_limit"] == "2.00000002"
    assert "spent" not in {
        key for key in budget.json() if key not in {"spent_estimated", "spent_billed"}
    }
    invalid_budget = governance_client.put(
        f"/api/v1/projects/{project_id}/budget",
        json={
            "currency": "usd",
            "soft_limit": "2",
            "hard_limit": "1",
            "period": "lifetime",
            "enabled": True,
        },
    )
    assert invalid_budget.status_code == 422

    plan = governance_client.post(f"/api/v1/projects/{project_id}/plan", json={})
    assert plan.status_code == 200
    usage = governance_client.get(f"/api/v1/projects/{project_id}/usage")
    assert usage.status_code == 200
    assert usage.json()["calls"] == 1
    assert usage.json()["total_tokens"] > 0
    assert usage.json()["estimated_cost"] == "0"
    calls = governance_client.get(f"/api/v1/projects/{project_id}/usage/calls")
    assert calls.status_code == 200
    assert calls.json()["meta"]["total_items"] == 1
    audit = calls.json()["items"][0]
    assert audit["prompt_name"] == "planner"
    assert "request_hash" not in audit
    assert "pricing_snapshot" not in audit
    assert "prompt" not in audit


def test_workflow_usage_uses_same_audit_records(governance_client: TestClient) -> None:
    project_id = _create_project(governance_client)
    assert governance_client.post(f"/api/v1/projects/{project_id}/plan", json={}).status_code == 200
    workflow = governance_client.post(
        f"/api/v1/projects/{project_id}/chapters/1/workflow",
        json={"max_revision_attempts": 1},
    )
    assert workflow.status_code == 201
    workflow_id = workflow.json()["workflow_run_id"]
    usage = governance_client.get(f"/api/v1/workflow-runs/{workflow_id}/usage")
    assert usage.status_code == 200
    assert usage.json()["calls"] >= 3
    assert usage.json()["total_tokens"] > 0
    assert governance_client.get("/api/v1/workflow-runs/999999/usage").status_code == 404


def test_pause_resume_does_not_duplicate_provider_calls_or_usage(
    governance_client: TestClient,
) -> None:
    project_id = _create_project(governance_client)
    assert governance_client.post(f"/api/v1/projects/{project_id}/plan", json={}).status_code == 200
    paused = governance_client.post(
        f"/api/v1/projects/{project_id}/chapters/1/workflow",
        json={"max_revision_attempts": 1, "pause_after_node": "generate_draft"},
    )
    assert paused.status_code == 201
    assert paused.json()["status"] == "paused"
    workflow_id = int(paused.json()["workflow_run_id"])
    session_factory = governance_client.app.state.session_factory
    with session_factory() as session:
        before = session.scalars(
            select(ProviderCall)
            .where(ProviderCall.workflow_run_id == workflow_id)
            .order_by(ProviderCall.id)
        ).all()
        before_signatures = {
            (item.idempotency_key, item.attempt, item.fallback_index) for item in before
        }
    assert before
    assert len(before_signatures) == len(before)

    resumed = governance_client.post(f"/api/v1/workflow-runs/{workflow_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"
    with session_factory() as session:
        after = session.scalars(
            select(ProviderCall)
            .where(ProviderCall.workflow_run_id == workflow_id)
            .order_by(ProviderCall.id)
        ).all()
        workflow = session.get(WorkflowRun, workflow_id)
        assert workflow is not None
        after_signatures = [
            (item.idempotency_key, item.attempt, item.fallback_index) for item in after
        ]
        assert len(after_signatures) == len(set(after_signatures))
        assert before_signatures <= set(after_signatures)
        assert workflow.provider_call_count == len(after)
        assert workflow.provider_input_tokens == sum(item.input_tokens for item in after)
        assert workflow.provider_output_tokens == sum(item.output_tokens for item in after)
        assert workflow.provider_estimated_cost == sum(
            (item.estimated_cost or Decimal("0") for item in after),
            Decimal("0"),
        )
        final_count = len(after)
        final_cost = workflow.provider_estimated_cost

    assert governance_client.post(f"/api/v1/workflow-runs/{workflow_id}/resume").status_code == 409
    with session_factory() as session:
        persisted = session.scalars(
            select(ProviderCall).where(ProviderCall.workflow_run_id == workflow_id)
        ).all()
        workflow = session.get(WorkflowRun, workflow_id)
        assert workflow is not None
        assert len(persisted) == final_count
        assert workflow.provider_estimated_cost == final_cost
