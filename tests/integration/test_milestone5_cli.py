"""Milestone 5 offline CLI and audit-query integration."""

import json
import socket
from pathlib import Path

import pytest

from storyforge.cli.app import main


def _payload(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)


def test_demo_m5_runs_three_scenarios_and_checkpoint_recovery_offline(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = str(tmp_path / "demo-m5.sqlite3")
    checkpoint = str(tmp_path / "demo-m5-checkpoints.sqlite3")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def deny_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("demo-m5 attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    assert (
        main(
            [
                "demo-m5",
                "--database",
                database,
                "--checkpoint",
                checkpoint,
                "--reset",
            ]
        )
        == 0
    )
    result = _payload(capsys)
    scenario_a = result["Scenario A"]
    scenario_b = result["Scenario B"]
    scenario_c = result["Scenario C"]
    recovery = result["Checkpoint recovery"]
    confirmation = result["database_confirmation"]
    assert isinstance(scenario_a, dict)
    assert isinstance(scenario_b, dict)
    assert isinstance(scenario_c, dict)
    assert isinstance(recovery, dict)
    assert isinstance(confirmation, dict)

    assert scenario_a["Workflow status"] == "completed"
    assert scenario_a["Accepted version"] == 1
    assert scenario_a["Revision attempts"] == 0
    assert scenario_b["Workflow status"] == "completed"
    assert scenario_b["Accepted version"] == 2
    assert scenario_b["Score"][1] > scenario_b["Score"][0]
    assert scenario_c["Workflow status"] == "completed_needs_review"
    assert scenario_c["Best version"] == 1
    assert scenario_c["Revision attempts"] == 2
    assert recovery["Paused after"] == "evaluate_draft"
    assert recovery["Final status"] == "completed"
    assert recovery["Duplicate versions"] == 0
    assert recovery["Duplicate evaluations"] == 0
    assert recovery["Duplicate facts"] == 0
    assert confirmation["accepted_facts_retrievable"] == 1
    assert confirmation["rejected_facts_retrievable"] == 0
    assert confirmation["conflicts"] == 2
    assert confirmation["conflicts_bound_to_versions"] is True
    assert confirmation["resolved_conflicts"] == 2
    assert confirmation["evaluations_bound_to_versions"] is True
    assert confirmation["future_facts_in_chapter_1_context"] == 0
    assert confirmation["checkpoint_contains_api_key"] is False
    assert confirmation["checkpoint_contains_chapter_body"] is False
    assert result["network_requests"] == 0
    assert result["api_key_required"] is False

    run_id = str(scenario_b["workflow_run_id"])
    project_id = str(scenario_b["project_id"])
    assert (
        main(
            [
                "workflow-status",
                "--database",
                database,
                "--checkpoint",
                checkpoint,
                "--workflow-run-id",
                run_id,
            ]
        )
        == 0
    )
    assert _payload(capsys)["accepted_version"] == 2

    assert (
        main(
            [
                "workflow-history",
                "--database",
                database,
                "--checkpoint",
                checkpoint,
                "--workflow-run-id",
                run_id,
            ]
        )
        == 0
    )
    history = _payload(capsys)
    assert history["events"]
    assert all("content" not in event for event in history["events"])

    assert (
        main(
            [
                "show-versions",
                "--database",
                database,
                "--project-id",
                project_id,
                "--chapter-number",
                "1",
            ]
        )
        == 0
    )
    versions = _payload(capsys)
    assert [item["status"] for item in versions["versions"]] == ["rejected", "accepted"]

    assert (
        main(
            [
                "compare-versions",
                "--database",
                database,
                "--workflow-run-id",
                run_id,
            ]
        )
        == 0
    )
    comparisons = _payload(capsys)["comparisons"]
    assert len(comparisons) == 1
    assert comparisons[0]["decision"] == "accept_new"
