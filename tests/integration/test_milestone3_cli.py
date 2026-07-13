"""Exercise every documented milestone-three CLI command in-process."""

import json
from pathlib import Path

from storyforge.cli.app import main


def _payload(capsys: object) -> dict[str, object]:
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    return json.loads(captured.out)


def test_individual_cli_commands_execute_against_one_sqlite_database(
    tmp_path: Path, capsys: object
) -> None:
    database = str(tmp_path / "commands.sqlite3")
    assert (
        main(
            [
                "create-project",
                "--database",
                database,
                "--title",
                "Test Story",
                "--genre",
                "Mystery",
                "--premise",
                "A keeper finds a moving lighthouse.",
                "--chapters",
                "3",
            ]
        )
        == 0
    )
    project_id = int(_payload(capsys)["project_id"])

    assert main(["plan", "--database", database, "--project-id", str(project_id)]) == 0
    assert _payload(capsys)["chapters"] == 3

    assert (
        main(
            [
                "show-context",
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
    assert _payload(capsys)["author_secrets"] == []

    generate_args = [
        "generate-chapter",
        "--database",
        database,
        "--project-id",
        str(project_id),
        "--chapter-number",
        "1",
    ]
    assert main(generate_args) == 0
    assert _payload(capsys)["status"] == "generated"
    assert main(generate_args) == 2
    assert "already has content" in capsys.readouterr().err  # type: ignore[attr-defined]

    assert (
        main(
            [
                "show-chapter",
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
    chapter = _payload(capsys)
    assert chapter["facts"] == 1
    assert chapter["versions"] == 1


def test_demo_m3_is_repeatable_and_reports_persisted_results(
    tmp_path: Path, capsys: object
) -> None:
    database = str(tmp_path / "demo.sqlite3")
    command = ["demo-m3", "--database", database]

    assert main(command) == 0
    first = _payload(capsys)
    assert first["mock_llm_calls"] == 3
    assert first["chapter"]["facts"] == 1  # type: ignore[index]

    assert main(command) == 0
    second = _payload(capsys)
    assert second["project_id"] == 2
