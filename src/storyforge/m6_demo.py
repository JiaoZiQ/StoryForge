"""Clean SQLite runner for the complete offline Milestone 6 demonstration."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from alembic.config import Config

from storyforge.application import DemoApplicationService
from storyforge.database import create_database_engine, create_session_factory
from storyforge.schemas.api import DemoM6Response
from storyforge.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_demo_m6(database: Path | None = None, *, reset: bool = False) -> DemoM6Response:
    """Migrate a clean local database, run MockLLM, and return verified projections."""
    if database is None:
        with TemporaryDirectory(prefix="storyforge-m6-") as directory:
            return _run_demo(Path(directory) / "storyforge.sqlite3", reset=True)
    return _run_demo(database.expanduser().resolve(), reset=reset)


def _run_demo(path: Path, *, reset: bool) -> DemoM6Response:
    checkpoint = path.with_name(f"{path.stem}.checkpoints.sqlite3")
    if reset:
        for removable in (path, checkpoint):
            removable.unlink(missing_ok=True)
    database_url = f"sqlite:///{path.as_posix()}"
    _upgrade(database_url)
    settings = Settings(
        environment="test",
        database_url=database_url,
        llm_provider="mock",
        mock_workflow_scenario="improve",
        checkpoint_path=checkpoint,
        enable_http_logging=False,
    )
    engine = create_database_engine(database_url)
    try:
        return DemoApplicationService(create_session_factory(engine), settings).run()
    finally:
        engine.dispose()


def _upgrade(database_url: str) -> None:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
