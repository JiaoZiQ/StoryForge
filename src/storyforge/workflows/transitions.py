"""Centralized WorkflowRun state transitions and error redaction."""

import re

from storyforge.enums import WorkflowRunStatus
from storyforge.exceptions import InvalidStateError
from storyforge.models import WorkflowRun

_ALLOWED: dict[WorkflowRunStatus, set[WorkflowRunStatus]] = {
    WorkflowRunStatus.PENDING: {
        WorkflowRunStatus.RUNNING,
        WorkflowRunStatus.CANCELLED,
        WorkflowRunStatus.FAILED,
    },
    WorkflowRunStatus.RUNNING: {
        WorkflowRunStatus.PAUSED,
        WorkflowRunStatus.COMPLETED,
        WorkflowRunStatus.COMPLETED_NEEDS_REVIEW,
        WorkflowRunStatus.FAILED,
        WorkflowRunStatus.CANCELLED,
    },
    WorkflowRunStatus.PAUSED: {
        WorkflowRunStatus.RUNNING,
        WorkflowRunStatus.CANCELLED,
        WorkflowRunStatus.FAILED,
    },
    WorkflowRunStatus.COMPLETED: set(),
    WorkflowRunStatus.COMPLETED_NEEDS_REVIEW: set(),
    WorkflowRunStatus.CANCELLED: set(),
    WorkflowRunStatus.FAILED: set(),
    WorkflowRunStatus.SUCCEEDED: set(),
    WorkflowRunStatus.NEEDS_HUMAN_REVIEW: set(),
}
_SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*[^\s,;]+")
_BEARER_RE = re.compile(r"(?i)bearer\s+[a-z0-9._~+\-/=]+")


def transition_workflow(run: WorkflowRun, target: WorkflowRunStatus) -> None:
    """Apply one legal transition or reject it explicitly."""
    if run.status is target:
        return
    if target not in _ALLOWED[run.status]:
        raise InvalidStateError(f"Workflow cannot transition from {run.status} to {target}")
    run.status = target


def redact_error(value: object, *, limit: int = 500) -> str:
    """Return bounded, credential-free workflow error text."""
    text = _BEARER_RE.sub("Bearer [REDACTED]", str(value))
    text = _SECRET_RE.sub(r"\1=[REDACTED]", text)
    return text[:limit]
