"""Bounded Milestone 9 product-demo projections."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl


class DemoM9Response(BaseModel):
    """Safe summary for preparing a browser-visible demonstration project."""

    model_config = ConfigDict(extra="forbid")

    database_backend: Literal["PostgreSQL"]
    project_id: int
    workflow_status: str
    accepted_version: int
    revision_attempts: int
    final_score: float
    memory_chunks: int
    graph_entities: int
    graph_relations: int
    retrieval_hits: int
    frontend_url: HttpUrl
