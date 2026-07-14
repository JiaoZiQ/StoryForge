"""Grouped CLI and demo-m6 integration checks."""

import json
import socket
from pathlib import Path

import pytest

from storyforge.cli import m6 as cli_m6
from storyforge.cli.app import main
from storyforge.llm.exceptions import LLMTimeoutError


def _stdout_json(capsys: object) -> dict[str, object]:
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    return json.loads(captured.out)


def test_demo_m6_is_offline_json_and_has_no_duplicate_memory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "demo-m6.sqlite3"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("STORYFORGE_LLM_API_KEY", raising=False)

    def deny_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("demo-m6 attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    assert (
        main(
            [
                "demo-m6",
                "--database",
                str(database),
                "--reset",
                "--output",
                "json",
            ]
        )
        == 0
    )
    payload = _stdout_json(capsys)
    assert payload["plan_chapters"] == 3
    assert payload["versions"] == 2
    assert payload["accepted_version"] == 2
    assert payload["evaluation"]["mechanical_score"] > 0  # type: ignore[index,operator]
    assert payload["evaluation"]["critic_score"] > 0  # type: ignore[index,operator]
    assert payload["evaluation"]["consistency_score"] > 0  # type: ignore[index,operator]
    assert payload["evaluation"]["passed"] is True  # type: ignore[index]
    assert payload["workflow"]["status"] == "completed"  # type: ignore[index]
    assert payload["workflow"]["revision_attempt"] == 1  # type: ignore[index]
    assert payload["candidate_facts_visible"] == 0
    assert payload["future_facts_visible"] == 0
    assert payload["duplicate_versions"] == 0
    assert payload["duplicate_evaluations"] == 0
    assert payload["duplicate_conflicts"] == 0
    assert payload["duplicate_facts"] == 0


def test_grouped_cli_reuses_application_services_and_exit_codes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORYFORGE_ENVIRONMENT", "test")
    monkeypatch.setenv("STORYFORGE_LLM_PROVIDER", "mock")
    monkeypatch.delenv("STORYFORGE_CHECKPOINT_PATH", raising=False)
    with pytest.raises(SystemExit) as help_exit:
        main(["--help"])
    assert help_exit.value.code == 0
    assert "project" in capsys.readouterr().out

    database = str(tmp_path / "grouped.sqlite3")
    create = [
        "project",
        "create",
        "--database",
        database,
        "--title",
        "Grouped CLI",
        "--genre",
        "mystery",
        "--premise",
        "An archive mystery.",
        "--chapters",
        "3",
        "--words",
        "300",
        "--output",
        "json",
    ]
    assert main(create) == 0
    project_id = int(_stdout_json(capsys)["id"])
    assert (
        main(
            [
                "plan",
                "generate",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--output",
                "json",
            ]
        )
        == 0
    )
    assert len(_stdout_json(capsys)["chapter_plans"]) == 3  # type: ignore[arg-type]
    assert (
        main(
            [
                "chapter",
                "list",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--output",
                "json",
            ]
        )
        == 0
    )
    chapter_page = _stdout_json(capsys)
    assert chapter_page["meta"]["total_items"] == 3  # type: ignore[index]
    assert (
        main(
            [
                "plan",
                "show",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--output",
                "json",
            ]
        )
        == 0
    )
    assert len(_stdout_json(capsys)["chapter_plans"]) == 3  # type: ignore[arg-type]
    assert (
        main(
            [
                "workflow",
                "run",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--chapter-number",
                "1",
                "--scenario",
                "improve",
                "--max-revision-attempts",
                "2",
                "--output",
                "json",
            ]
        )
        == 0
    )
    workflow = _stdout_json(capsys)
    workflow_id = int(workflow["workflow_run_id"])
    assert workflow["status"] == "completed"

    query_commands = [
        (
            [
                "project",
                "show",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--output",
                "json",
            ],
            "title",
        ),
        (
            [
                "chapter",
                "show",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--chapter-number",
                "1",
                "--output",
                "json",
            ],
            "accepted_version",
        ),
        (
            [
                "chapter",
                "context",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--chapter-number",
                "1",
                "--output",
                "json",
            ],
            "known_fact_count",
        ),
        (
            [
                "workflow",
                "status",
                "--database",
                database,
                "--workflow-run-id",
                str(workflow_id),
                "--output",
                "json",
            ],
            "status",
        ),
        (
            [
                "workflow",
                "events",
                "--database",
                database,
                "--workflow-run-id",
                str(workflow_id),
                "--output",
                "json",
            ],
            "items",
        ),
        (
            [
                "fact",
                "list",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--output",
                "json",
            ],
            "items",
        ),
    ]
    for command_args, required_key in query_commands:
        assert main(command_args) == 0
        assert required_key in _stdout_json(capsys)

    assert (
        main(
            [
                "chapter",
                "versions",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--chapter-number",
                "1",
                "--output",
                "json",
            ]
        )
        == 0
    )
    versions = _stdout_json(capsys)["items"]
    assert isinstance(versions, list)
    assert len(versions) == 2
    assert (
        main(
            [
                "chapter",
                "diff",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--chapter-number",
                "1",
                "--version-id",
                str(versions[0]["id"]),
                "--old-version-id",
                str(versions[1]["id"]),
                "--output",
                "json",
            ]
        )
        == 0
    )
    assert _stdout_json(capsys)["changed_line_count"] > 0  # type: ignore[operator]

    assert (
        main(
            [
                "evaluation",
                "list",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--chapter-number",
                "1",
                "--output",
                "json",
            ]
        )
        == 0
    )
    evaluations = _stdout_json(capsys)["items"]
    assert isinstance(evaluations, list)
    assert len(evaluations) == 2
    assert (
        main(
            [
                "evaluation",
                "show",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--chapter-number",
                "1",
                "--evaluation-id",
                str(evaluations[0]["id"]),
                "--output",
                "json",
            ]
        )
        == 0
    )
    assert _stdout_json(capsys)["raw_scores"]

    assert (
        main(
            [
                "conflict",
                "list",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--output",
                "json",
            ]
        )
        == 0
    )
    conflicts = _stdout_json(capsys)["items"]
    assert isinstance(conflicts, list)
    assert conflicts
    assert (
        main(
            [
                "conflict",
                "resolve",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--conflict-id",
                str(conflicts[0]["id"]),
                "--note",
                "CLI review",
                "--output",
                "json",
            ]
        )
        == 0
    )
    assert _stdout_json(capsys)["status"] == "resolved"

    assert (
        main(
            [
                "project",
                "show",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--output",
                "human",
            ]
        )
        == 0
    )
    human = capsys.readouterr().out
    assert "title: Grouped CLI" in human
    assert "content:" not in human

    assert (
        main(
            [
                "workflow",
                "run",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--chapter-number",
                "2",
                "--scenario",
                "improve",
                "--pause-after-node",
                "evaluate_draft",
                "--output",
                "json",
            ]
        )
        == 0
    )
    paused_id = str(_stdout_json(capsys)["workflow_run_id"])
    assert (
        main(
            [
                "workflow",
                "resume",
                "--database",
                database,
                "--workflow-run-id",
                paused_id,
                "--output",
                "json",
            ]
        )
        == 0
    )
    assert _stdout_json(capsys)["status"] in {"completed", "completed_needs_review"}

    assert (
        main(
            [
                "workflow",
                "run",
                "--database",
                database,
                "--project-id",
                str(project_id),
                "--chapter-number",
                "3",
                "--scenario",
                "improve",
                "--pause-after-node",
                "generate_draft",
                "--output",
                "json",
            ]
        )
        == 0
    )
    cancelled_id = str(_stdout_json(capsys)["workflow_run_id"])
    assert (
        main(
            [
                "workflow",
                "cancel",
                "--database",
                database,
                "--workflow-run-id",
                cancelled_id,
                "--output",
                "json",
            ]
        )
        == 0
    )
    assert _stdout_json(capsys)["status"] == "cancelled"
    assert (
        main(
            [
                "project",
                "show",
                "--database",
                database,
                "--project-id",
                "999",
                "--output",
                "json",
            ]
        )
        == 3
    )
    assert "resource_not_found" in capsys.readouterr().err  # type: ignore[attr-defined]
    assert main(create) == 0
    duplicate_project = int(_stdout_json(capsys)["id"])
    assert (
        main(
            [
                "plan",
                "generate",
                "--database",
                database,
                "--project-id",
                str(duplicate_project),
                "--output",
                "json",
            ]
        )
        == 0
    )
    _stdout_json(capsys)
    assert (
        main(
            [
                "plan",
                "generate",
                "--database",
                database,
                "--project-id",
                str(duplicate_project),
                "--output",
                "json",
            ]
        )
        == 4
    )
    assert "state_conflict" in capsys.readouterr().err  # type: ignore[attr-defined]


def test_cli_provider_error_uses_stable_code_without_secret(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(args: object) -> dict[str, object]:
        del args
        raise LLMTimeoutError("provider leaked sk-cli-secret", attempts=1)

    monkeypatch.setattr(cli_m6, "_project_create", fail)
    exit_code = main(
        [
            "project",
            "create",
            "--database",
            str(tmp_path / "error.sqlite3"),
            "--title",
            "Error",
            "--genre",
            "mystery",
            "--premise",
            "Error path",
            "--chapters",
            "3",
        ]
    )
    assert exit_code == 5
    error = capsys.readouterr().err
    assert "provider_unavailable" in error
    assert "sk-cli-secret" not in error
