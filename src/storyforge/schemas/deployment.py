"""Deployment and PostgreSQL demonstration projections for Milestone 7."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class DemoM7Response(BaseModel):
    """Content-free summary of one PostgreSQL-backed MockLLM workflow."""

    model_config = ConfigDict(extra="forbid")

    database_backend: Literal["PostgreSQL"]
    migration_revision: str
    project_id: int
    workflow_run_id: int
    workflow_status: str
    accepted_version: int
    revision_attempts: int
    versions: int
    evaluations: int
    conflicts: int
    accepted_facts: int
    candidate_facts_visible: int
    future_facts_visible: int
    duplicate_versions: int
    duplicate_evaluations: int
    duplicate_conflicts: int
    duplicate_facts: int
    final_score: float
