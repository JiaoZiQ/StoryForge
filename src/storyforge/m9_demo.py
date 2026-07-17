"""Milestone 9 browser-demo data preparation."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from pydantic import HttpUrl
from sqlalchemy import select

from storyforge.database import create_database_engine, create_session_factory
from storyforge.exceptions import ConfigurationError, InvalidStateError
from storyforge.m8_demo import run_demo_m8
from storyforge.models import Chapter, Evaluation
from storyforge.schemas.frontend import DemoM9Response
from storyforge.settings import Settings


def run_demo_m9(
    settings: Settings | None = None,
    *,
    frontend_base_url: str = "http://localhost:3000",
) -> DemoM9Response:
    """Prepare one complete M9 project using the proven offline M8 pipeline."""
    configured = settings or Settings.from_env()
    m8 = run_demo_m8(configured)
    engine = create_database_engine(configured.database_url)
    try:
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            final_score = session.scalar(
                select(Evaluation.overall_score)
                .join(Chapter, Evaluation.chapter_id == Chapter.id)
                .where(Chapter.project_id == m8.project_id)
                .order_by(Evaluation.id.desc())
                .limit(1)
            )
        if final_score is None:
            raise InvalidStateError("demo-m9 project has no evaluation score")
        return DemoM9Response(
            database_backend=m8.database_backend,
            project_id=m8.project_id,
            workflow_status=m8.workflow_status,
            accepted_version=m8.accepted_version,
            revision_attempts=m8.revision_attempts,
            final_score=float(final_score),
            memory_chunks=m8.memory_chunks,
            graph_entities=m8.graph_entities,
            graph_relations=m8.graph_relations,
            retrieval_hits=m8.retrieval.final_hits,
            frontend_url=HttpUrl(_project_url(frontend_base_url, m8.project_id)),
        )
    finally:
        engine.dispose()


def _project_url(frontend_base_url: str, project_id: int) -> str:
    parsed = urlsplit(frontend_base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError("frontend URL must be an absolute HTTP or HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError("frontend URL cannot contain credentials, query, or fragment")
    base_path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, f"{base_path}/projects/{project_id}", "", ""))
