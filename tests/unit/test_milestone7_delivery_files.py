"""Static delivery-contract tests for Docker, Compose, CI, and safe cleanup."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_is_locked_multistage_non_root_and_exec_form() -> None:
    content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "python:3.12.12-slim-bookworm" in content
    assert content.count("FROM ") >= 3
    assert "uv sync --locked --no-dev --no-editable" in content
    assert "USER 10001:10001" in content
    assert 'CMD ["storyforge-api"]' in content
    assert "COPY . ." not in content


def test_dockerignore_excludes_sensitive_and_local_artifacts() -> None:
    lines = set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())
    assert {".git", ".env", ".venv", "*.sqlite3", "tests"} <= lines
    assert "!.env.example" in lines


def test_compose_has_health_gated_migration_and_named_volume() -> None:
    document = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = document["services"]
    assert services["postgres"]["image"] == "pgvector/pgvector:0.8.2-pg16-bookworm"
    assert services["postgres"]["healthcheck"]
    assert services["migrate"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert services["api"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["api"]["healthcheck"]
    assert "storyforge_postgres_data" in document["volumes"]
    assert all(".env" not in str(service.get("volumes", [])) for service in services.values())


def test_ci_has_quality_postgres_and_docker_jobs_without_real_secret() -> None:
    content = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    document = yaml.safe_load(content)
    jobs = document["jobs"]
    assert {"quality", "postgres-tests", "docker-build"} <= set(jobs)
    assert "3.12" in content
    assert "uv sync --locked --all-groups" in content
    assert "ruff format --check ." in content
    assert "mypy src" in content
    assert "pytest" in content
    assert "pgvector/pgvector:0.8.2-pg16-bookworm" in content
    assert "storyforge demo-m10 --output json" in content
    assert "alembic upgrade head" in content
    assert "alembic check" in content
    assert "docker build" in content
    assert "STORYFORGE_LLM_PROVIDER: mock" in content
    assert "OPENAI_API_KEY" not in content


def test_clean_script_does_not_remove_databases_or_env() -> None:
    script = (ROOT / "scripts/clean.py").read_text(encoding="utf-8")
    assert "*.sqlite" not in script
    assert '".env"' not in script
    assert "docker compose" not in script.casefold()
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/clean.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
