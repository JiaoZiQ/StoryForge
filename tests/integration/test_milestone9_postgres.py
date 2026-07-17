"""Real PostgreSQL acceptance for the M9 browser-demo preparation command."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import make_url

from storyforge.m9_demo import run_demo_m9
from storyforge.settings import Settings

pytestmark = pytest.mark.postgres
ROOT = Path(__file__).resolve().parents[2]


def _test_url() -> str:
    value = os.getenv("STORYFORGE_POSTGRES_TEST_URL", "")
    if not value:
        pytest.skip("STORYFORGE_POSTGRES_TEST_URL is not configured")
    if not (make_url(value).database or "").casefold().endswith("_test"):
        pytest.fail("PostgreSQL tests require a database name ending in '_test'")
    return value


def test_demo_m9_prepares_a_safe_browser_project(tmp_path: Path) -> None:
    database_url = _test_url()
    os.environ["DATABASE_URL"] = database_url
    config = Config(str(ROOT / "alembic.ini"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    settings = Settings(
        environment="test",
        database_url=database_url,
        llm_provider="mock",
        embedding_provider="mock",
        embedding_dimensions=64,
        checkpoint_path=tmp_path / "m9-checkpoints.sqlite3",
    )
    try:
        result = run_demo_m9(settings, frontend_base_url="http://web.test:3000")
        assert result.database_backend == "PostgreSQL"
        assert result.workflow_status == "completed"
        assert result.revision_attempts >= 1
        assert result.accepted_version >= 2
        assert result.final_score >= 7
        assert result.memory_chunks > 0
        assert result.graph_entities > 0
        assert result.graph_relations > 0
        assert result.retrieval_hits > 0
        assert str(result.frontend_url) == (f"http://web.test:3000/projects/{result.project_id}")
        assert "content" not in result.model_dump(mode="json")
    finally:
        command.downgrade(config, "base")
