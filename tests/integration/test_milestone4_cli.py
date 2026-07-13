"""Milestone-four offline CLI integration tests."""

import json
import socket
from pathlib import Path

import pytest

from storyforge.cli.app import main


def _payload(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)


def test_demo_m4_is_offline_persists_both_evaluations_and_is_repeatable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = str(tmp_path / "demo-m4.sqlite3")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def deny_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("demo-m4 attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    command = ["demo-m4", "--database", database]
    assert main([*command, "--reset"]) == 0
    first = _payload(capsys)

    normal = first["Normal chapter evaluation"]
    conflict = first["Conflict chapter evaluation"]
    confirmation = first["database_confirmation"]
    assert isinstance(normal, dict) and isinstance(conflict, dict)
    assert isinstance(confirmation, dict)
    assert normal["Passed"] is True
    assert normal["Recommended action"] == "accept"
    assert conflict["Passed"] is False
    assert conflict["Conflicts detected"] >= 2
    assert conflict["Critical conflicts"] >= 1
    assert conflict["Final score"] <= 5
    assert conflict["Recommended action"] in {"revise", "human_review"}
    assert confirmation == {
        "evaluations": 2,
        "evaluation_issues": 3,
        "conflicts": 2,
        "raw_scores_present": True,
        "weighted_scores_present": True,
        "evaluator_versions_present": True,
        "prompt_versions_present": True,
    }
    assert first["offline_mock"] is True
    assert first["api_key_required"] is False
    assert first["future_fact_records_after_chapter_2"] == 0

    assert main(command) == 0
    second = _payload(capsys)
    assert second["project_id"] != first["project_id"]
    assert second["database_confirmation"] == confirmation


def test_evaluate_show_list_and_update_conflict_commands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = str(tmp_path / "commands-m4.sqlite3")
    assert main(["demo-m4", "--database", database, "--reset"]) == 0
    demo = _payload(capsys)
    project_id = int(demo["project_id"])

    assert (
        main(
            [
                "evaluate-chapter",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--chapter-number",
                "1",
            ]
        )
        == 0
    )
    repeated = _payload(capsys)
    assert repeated["evaluation_version"] == 2

    assert (
        main(
            [
                "show-evaluation",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--chapter-number",
                "1",
                "--latest",
            ]
        )
        == 0
    )
    shown = _payload(capsys)
    assert len(shown["evaluations"]) == 1

    assert (
        main(
            [
                "list-conflicts",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--status",
                "open",
            ]
        )
        == 0
    )
    listed = _payload(capsys)
    assert listed["count"] == 2
    conflict_id = int(listed["conflicts"][0]["id"])

    assert (
        main(
            [
                "update-conflict",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--conflict-id",
                str(conflict_id),
                "--status",
                "ignored",
            ]
        )
        == 0
    )
    updated = _payload(capsys)
    assert updated["status"] == "ignored"
