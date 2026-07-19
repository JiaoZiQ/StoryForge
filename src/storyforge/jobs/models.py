"""Typed job definitions and small execution results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from storyforge.enums import JobType


class JobDefinition(BaseModel):
    """One allowlisted mapping from public job type to an internal handler."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_type: JobType
    handler_name: str = Field(min_length=1, max_length=100)
    queue_name: str = Field(min_length=1, max_length=100)
    max_attempts: int = Field(ge=1, le=20)
    timeout_seconds: int = Field(ge=1, le=86_400)
    retry_policy: str = Field(min_length=1, max_length=100)
    cancellable: bool
    resumable: bool
    idempotent: bool


class JobHandlerResult(BaseModel):
    """Bounded result persisted by a handler; large domain objects stay elsewhere."""

    model_config = ConfigDict(extra="forbid")

    resource_ids: dict[str, int | str | None] = Field(default_factory=dict)
    summary: str = Field(default="", max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobCreationResult(BaseModel):
    """Creation outcome with explicit idempotency reuse."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: int
    reused: bool


def normalized_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Return a JSON-compatible, deterministic payload projection."""
    return {str(key): payload[key] for key in sorted(payload)}
