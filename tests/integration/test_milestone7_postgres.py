"""Explicit PostgreSQL 16 integration coverage for Milestone 7."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, make_url, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from tests._factories import create_story_graph, make_project

from storyforge.api.app import create_app
from storyforge.cli.app import main
from storyforge.database import create_database_engine, create_session_factory
from storyforge.enums import ChapterStatus, WorkflowRunStatus
from storyforge.m7_demo import run_demo_m7
from storyforge.migrations import MIGRATION_HEAD
from storyforge.models import Base, Chapter, Project, WorkflowRun
from storyforge.repositories import ProjectRepository
from storyforge.settings import Settings

pytestmark = pytest.mark.postgres
ROOT = Path(__file__).resolve().parents[2]


def _test_url() -> str:
    value = os.getenv("STORYFORGE_POSTGRES_TEST_URL", "")
    if not value:
        pytest.skip("STORYFORGE_POSTGRES_TEST_URL is not configured")
    database = make_url(value).database or ""
    if not database.casefold().endswith("_test"):
        pytest.fail("PostgreSQL tests require a database name ending in '_test'")
    return value


@pytest.fixture(scope="module")
def postgres_engine() -> Iterator[Engine]:
    database_url = _test_url()
    os.environ["DATABASE_URL"] = database_url
    config = Config(str(ROOT / "alembic.ini"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_database_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()
        command.downgrade(config, "base")


@pytest.fixture(autouse=True)
def clean_database(postgres_engine: Engine) -> Iterator[None]:
    tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    with postgres_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def postgres_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=_test_url(),
        llm_provider="mock",
        mock_mode=True,
        mock_workflow_scenario="improve",
        checkpoint_path=tmp_path / "postgres-checkpoints.sqlite3",
    )


def test_postgres_migrations_are_at_unique_head_and_match_metadata(
    postgres_engine: Engine,
) -> None:
    inspector = inspect(postgres_engine)
    assert set(Base.metadata.tables) <= set(inspector.get_table_names())
    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == MIGRATION_HEAD
    command.check(Config(str(ROOT / "alembic.ini")))
    active_indexes = {
        index["name"] for index in inspector.get_indexes("workflow_runs") if index["unique"]
    }
    assert "uq_workflow_runs_active_chapter" in active_indexes


def test_postgres_types_constraints_cascade_rollback_pagination_and_sorting(
    postgres_engine: Engine,
) -> None:
    session_factory = create_session_factory(postgres_engine)
    with session_factory.begin() as session:
        graph = create_story_graph(session)
        graph.project.themes = ["memory", "tides"]
        graph.story_rule.structured_metadata = {"forbidden_predicate": "fire_magic"}
        graph.story_rule.active = True
        project_id = graph.project.id
    with session_factory() as session:
        restored = ProjectRepository(session).get(project_id)
        assert restored is not None
        assert restored.themes == ["memory", "tides"]
        assert restored.created_at.tzinfo is not None
        assert restored.story_rules[0].structured_metadata["forbidden_predicate"] == "fire_magic"
        assert restored.story_rules[0].active is True

    with pytest.raises(RuntimeError, match="rollback"):
        with session_factory.begin() as session:
            session.add(make_project(title="Must Roll Back"))
            session.flush()
            raise RuntimeError("rollback")
    with session_factory() as session:
        assert session.scalar(select(func.count(Project.id))) == 1

    with session_factory.begin() as session:
        session.add_all([make_project(title="Zulu"), make_project(title="Alpha")])
    with session_factory() as session:
        page = ProjectRepository(session).page_filtered(
            page=1,
            page_size=2,
            sort="title",
            order="asc",
        )
        assert page.total_items == 3
        assert [item.title for item in page.items] == ["Alpha", "The Clockwork Harbor"]
        root = ProjectRepository(session).get(project_id)
        assert root is not None
        ProjectRepository(session).delete(root)
        session.commit()
        assert session.scalar(select(func.count(Chapter.id))) == 0


def test_postgres_enforces_one_active_workflow_and_allows_completed_history(
    postgres_engine: Engine,
) -> None:
    session_factory = create_session_factory(postgres_engine)
    with session_factory.begin() as session:
        project = Project(
            title="Workflow constraint",
            genre="mystery",
            premise="Two processes race for one chapter.",
            target_chapters=1,
            target_words_per_chapter=300,
        )
        session.add(project)
        session.flush()
        chapter = Chapter(
            project_id=project.id,
            chapter_number=1,
            title="One",
            outline="Race safely.",
            status=ChapterStatus.PLANNED,
        )
        session.add(chapter)
        session.flush()
        session.add(
            WorkflowRun(
                project_id=project.id,
                chapter_id=chapter.id,
                current_node="initialize_workflow",
                status=WorkflowRunStatus.RUNNING,
            )
        )
    with pytest.raises(IntegrityError):
        with session_factory.begin() as session:
            session.add(
                WorkflowRun(
                    project_id=project.id,
                    chapter_id=chapter.id,
                    current_node="initialize_workflow",
                    status=WorkflowRunStatus.PAUSED,
                )
            )
    with session_factory.begin() as session:
        active = session.scalar(select(WorkflowRun))
        assert active is not None
        active.status = WorkflowRunStatus.COMPLETED
        session.add(
            WorkflowRun(
                project_id=project.id,
                chapter_id=chapter.id,
                current_node="initialize_workflow",
                status=WorkflowRunStatus.PENDING,
            )
        )


def test_postgres_api_workflow_is_future_safe_and_content_minimal(
    postgres_settings: Settings,
) -> None:
    with TestClient(create_app(postgres_settings)) as client:
        created = client.post(
            "/api/v1/projects",
            json={
                "title": "Postgres API",
                "genre": "mystery",
                "premise": "An archivist audits a sealed network.",
                "target_chapters": 3,
                "target_words_per_chapter": 300,
                "language": "en",
            },
        )
        assert created.status_code == 201
        project_id = int(created.json()["id"])
        assert client.post(f"/api/v1/projects/{project_id}/plan", json={}).status_code == 200
        context = client.get(f"/api/v1/projects/{project_id}/chapters/1/context")
        assert context.status_code == 200
        assert context.json()["known_fact_count"] == 0
        workflow = client.post(
            f"/api/v1/projects/{project_id}/chapters/1/workflow",
            json={"max_revision_attempts": 2},
        )
        assert workflow.status_code == 201
        assert workflow.json()["status"] == "completed"
        chapters = client.get(f"/api/v1/projects/{project_id}/chapters")
        assert all("content" not in item for item in chapters.json()["items"])
        versions = client.get(f"/api/v1/projects/{project_id}/chapters/1/versions")
        assert len(versions.json()["items"]) == 2
        assert all("content" not in item for item in versions.json()["items"])
        facts = client.get(f"/api/v1/projects/{project_id}/facts")
        assert {item["status"] for item in facts.json()["items"]} == {"accepted"}


def test_demo_m7_is_repeatable_without_candidate_future_or_duplicate_side_effects(
    postgres_settings: Settings,
) -> None:
    first = run_demo_m7(postgres_settings)
    second = run_demo_m7(postgres_settings)
    for result in (first, second):
        assert result.database_backend == "PostgreSQL"
        assert result.migration_revision == MIGRATION_HEAD
        assert result.workflow_status == "completed"
        assert result.revision_attempts >= 1
        assert result.versions >= 2
        assert result.evaluations >= 2
        assert result.accepted_facts >= 1
        assert result.candidate_facts_visible == 0
        assert result.future_facts_visible == 0
        assert result.duplicate_versions == 0
        assert result.duplicate_evaluations == 0
        assert result.duplicate_conflicts == 0
        assert result.duplicate_facts == 0
    assert first.project_id != second.project_id


def test_demo_m7_cli_emits_standard_json_without_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_url = _test_url()
    monkeypatch.setenv("STORYFORGE_ENVIRONMENT", "test")
    monkeypatch.setenv("STORYFORGE_DATABASE_URL", database_url)
    monkeypatch.setenv("STORYFORGE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("STORYFORGE_MOCK_MODE", "true")
    monkeypatch.setenv("STORYFORGE_CHECKPOINT_PATH", str(tmp_path / "cli-checkpoint.sqlite3"))
    monkeypatch.delenv("STORYFORGE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert main(["demo-m7", "--output", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["database_backend"] == "PostgreSQL"
    assert payload["workflow_status"] == "completed"
    assert payload["candidate_facts_visible"] == 0
    assert payload["future_facts_visible"] == 0
