"""PostgreSQL-backed, network-free deployment demonstration."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import make_url

from storyforge.application import DemoApplicationService, SystemApplicationService
from storyforge.database import (
    create_database_engine,
    create_session_factory,
    normalize_database_url,
)
from storyforge.exceptions import ConfigurationError
from storyforge.schemas.deployment import DemoM7Response
from storyforge.settings import Settings


def run_demo_m7(settings: Settings | None = None) -> DemoM7Response:
    """Run the M6 application path against the configured PostgreSQL database."""
    configured = settings or Settings.from_env()
    backend = make_url(normalize_database_url(configured.database_url)).get_backend_name()
    if backend != "postgresql":
        raise ConfigurationError("demo-m7 requires a PostgreSQL database")
    if configured.llm_provider != "mock" or not configured.mock_mode:
        raise ConfigurationError("demo-m7 requires explicit MockLLM mode")

    engine = create_database_engine(configured.database_url)
    try:
        session_factory = create_session_factory(engine)
        readiness = SystemApplicationService(session_factory, configured).readiness()
        result = DemoApplicationService(session_factory, configured).run(
            project_title=f"Milestone 7 PostgreSQL {uuid4().hex[:12]}"
        )
    finally:
        engine.dispose()
    return DemoM7Response(
        database_backend="PostgreSQL",
        migration_revision=readiness.migration_revision,
        project_id=result.project.id,
        workflow_run_id=result.workflow.workflow_run_id,
        workflow_status=result.workflow.status.value,
        accepted_version=result.accepted_version,
        revision_attempts=result.workflow.revision_attempt,
        versions=result.versions,
        evaluations=result.evaluations,
        conflicts=result.evaluation.conflict_count,
        accepted_facts=result.accepted_facts,
        candidate_facts_visible=result.candidate_facts_visible,
        future_facts_visible=result.future_facts_visible,
        duplicate_versions=result.duplicate_versions,
        duplicate_evaluations=result.duplicate_evaluations,
        duplicate_conflicts=result.duplicate_conflicts,
        duplicate_facts=result.duplicate_facts,
        final_score=result.final_score,
    )
