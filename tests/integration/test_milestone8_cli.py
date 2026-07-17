"""Standard-JSON M8 CLI integration over the SQLite degraded path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from storyforge.cli.app import main


def _payload(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)


def test_memory_retrieval_and_graph_cli_use_application_services(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "m8-cli.sqlite3"
    database_url = f"sqlite:///{database.as_posix()}"
    common = ["--database", str(database), "--output", "json"]
    assert (
        main(
            [
                "project",
                "create",
                "--title",
                "M8 CLI",
                "--genre",
                "mystery",
                "--premise",
                "A key opens the tidal archive.",
                "--chapters",
                "3",
                "--words",
                "300",
                *common,
            ]
        )
        == 0
    )
    project_id = int(_payload(capsys)["id"])
    assert (
        main(
            [
                "plan",
                "generate",
                "--project-id",
                str(project_id),
                *common,
            ]
        )
        == 0
    )
    _payload(capsys)
    assert (
        main(
            [
                "workflow",
                "run",
                "--project-id",
                str(project_id),
                "--chapter-number",
                "1",
                "--scenario",
                "improve",
                "--max-revision-attempts",
                "2",
                *common,
            ]
        )
        == 0
    )
    workflow = _payload(capsys)
    accepted_version_id = int(workflow["accepted_version_id"])

    monkeypatch.setenv("STORYFORGE_ENVIRONMENT", "test")
    monkeypatch.setenv("STORYFORGE_DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("STORYFORGE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("STORYFORGE_EMBEDDING_PROVIDER", "mock")
    monkeypatch.delenv("STORYFORGE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("STORYFORGE_EMBEDDING_API_KEY", raising=False)

    commands = [
        ["memory", "status", "--project-id", str(project_id), "--output", "json"],
        ["memory", "list", "--project-id", str(project_id), "--output", "json"],
        [
            "memory",
            "reindex",
            "--project-id",
            str(project_id),
            "--chapter-version-id",
            str(accepted_version_id),
            "--output",
            "json",
        ],
        [
            "retrieval",
            "search",
            "--project-id",
            str(project_id),
            "--query",
            "Mara brass key",
            "--current-chapter",
            "2",
            "--character",
            "Mara",
            "--output",
            "json",
        ],
        ["graph", "entities", "--project-id", str(project_id), "--output", "json"],
        [
            "graph",
            "relations",
            "--project-id",
            str(project_id),
            "--current-chapter",
            "2",
            "--output",
            "json",
        ],
    ]
    payloads: list[dict[str, object]] = []
    for command in commands:
        assert main(command) == 0
        payloads.append(_payload(capsys))
    assert payloads[0]["items"]
    assert payloads[1]["items"]
    assert payloads[2]["results"]
    assert payloads[3]["degraded"] is True
    assert payloads[3]["hits"]
    assert payloads[4]["items"]
    relations = payloads[5]["items"]
    assert isinstance(relations, list) and relations
    assert '"embedding":' not in json.dumps(payloads[1], ensure_ascii=False).casefold()

    entity_id = int(payloads[4]["items"][0]["id"])  # type: ignore[index]
    assert (
        main(
            [
                "graph",
                "neighbors",
                "--project-id",
                str(project_id),
                "--entity-id",
                str(entity_id),
                "--current-chapter",
                "2",
                "--max-hops",
                "2",
                "--output",
                "json",
            ]
        )
        == 0
    )
    assert "relations" in _payload(capsys)
