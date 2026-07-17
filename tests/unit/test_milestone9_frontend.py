"""Milestone 9 browser-demo boundary tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from storyforge.cli.app import main
from storyforge.exceptions import ConfigurationError
from storyforge.m9_demo import _project_url
from storyforge.schemas.frontend import DemoM9Response

ROOT = Path(__file__).resolve().parents[2]


def _demo_response() -> DemoM9Response:
    return DemoM9Response(
        database_backend="PostgreSQL",
        project_id=42,
        workflow_status="completed",
        accepted_version=2,
        revision_attempts=1,
        final_score=8.25,
        memory_chunks=4,
        graph_entities=3,
        graph_relations=2,
        retrieval_hits=4,
        frontend_url="http://localhost:3000/projects/42",
    )


def test_project_url_is_bounded_and_preserves_a_safe_base_path() -> None:
    assert _project_url("https://example.test/storyforge/", 9) == (
        "https://example.test/storyforge/projects/9"
    )
    for unsafe in (
        "javascript:alert(1)",
        "http://user:password@example.test",
        "https://example.test?token=secret",
        "https://example.test/#fragment",
    ):
        with pytest.raises(ConfigurationError):
            _project_url(unsafe, 1)


def test_demo_m9_cli_outputs_standard_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("storyforge.cli.m9.run_demo_m9", lambda **_: _demo_response())
    assert (
        main(
            [
                "demo-m9",
                "--frontend-url",
                "http://localhost:3000",
                "--output",
                "json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["project_id"] == 42
    assert payload["frontend_url"] == "http://localhost:3000/projects/42"
    assert "content" not in payload
    assert "api_key" not in payload


def test_frontend_delivery_contract_is_safe_and_complete() -> None:
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert package["dependencies"]["next"] == "16.2.10"
    assert package["devDependencies"]["typescript"] == "5.9.3"
    assert package["scripts"]["check:api"]
    assert package["scripts"]["test:e2e"]

    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert set(services["api"]["networks"]) == {"storyforge_internal"}
    assert set(services["frontend"]["networks"]) == {"storyforge_internal"}
    assert set(services["gateway"]["networks"]) == {
        "storyforge_internal",
        "storyforge_ingress",
    }
    assert compose["networks"]["storyforge_internal"]["internal"] is True
    assert services["frontend"]["depends_on"]["api"]["condition"] == "service_healthy"

    frontend_dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    gateway_dockerfile = (ROOT / "deploy" / "ingress.Dockerfile").read_text(encoding="utf-8")
    assert "USER 10001:10001" in frontend_dockerfile
    assert "USER 10001:10001" in gateway_dockerfile
    assert "COPY .env" not in frontend_dockerfile
    assert "NEXT_PUBLIC_" not in (ROOT / "frontend" / ".env.example").read_text(encoding="utf-8")

    required_routes = (
        "projects/page.tsx",
        "projects/new/page.tsx",
        "projects/[projectId]/chapters/[chapterNumber]/page.tsx",
        "projects/[projectId]/workflow/[workflowRunId]/page.tsx",
        "projects/[projectId]/retrieval/page.tsx",
        "projects/[projectId]/graph/page.tsx",
        "system/page.tsx",
    )
    for route in required_routes:
        assert (ROOT / "frontend" / "app" / route).is_file()


def test_generated_openapi_has_unique_operation_ids() -> None:
    schema = json.loads((ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
    operation_ids = [
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == 40
    assert len(operation_ids) == len(set(operation_ids))
