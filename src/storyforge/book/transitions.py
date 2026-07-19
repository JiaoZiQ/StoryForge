"""Centralized legal transitions for full-book runs and snapshots."""

from __future__ import annotations

from datetime import datetime

from storyforge.enums import BookRunStatus
from storyforge.exceptions import InvalidStateError
from storyforge.models import BookRun
from storyforge.models.base import utc_now

_ALLOWED: dict[BookRunStatus, frozenset[BookRunStatus]] = {
    BookRunStatus.PENDING: frozenset(
        {
            BookRunStatus.PLANNING_VALIDATION,
            BookRunStatus.PAUSED,
            BookRunStatus.CANCELLED,
            BookRunStatus.FAILED,
        }
    ),
    BookRunStatus.PLANNING_VALIDATION: frozenset(
        {
            BookRunStatus.GENERATING,
            BookRunStatus.PAUSED,
            BookRunStatus.CANCEL_REQUESTED,
            BookRunStatus.FAILED,
        }
    ),
    BookRunStatus.GENERATING: frozenset(
        {
            BookRunStatus.GLOBAL_REVIEW,
            BookRunStatus.PAUSED,
            BookRunStatus.CANCEL_REQUESTED,
            BookRunStatus.COMPLETED_NEEDS_REVIEW,
            BookRunStatus.BUDGET_BLOCKED,
            BookRunStatus.FAILED,
        }
    ),
    BookRunStatus.PAUSED: frozenset(
        {
            BookRunStatus.PLANNING_VALIDATION,
            BookRunStatus.GENERATING,
            BookRunStatus.GLOBAL_REVIEW,
            BookRunStatus.CANCELLED,
        }
    ),
    BookRunStatus.GLOBAL_REVIEW: frozenset(
        {
            BookRunStatus.GLOBAL_REVISION,
            BookRunStatus.COMPLETED,
            BookRunStatus.COMPLETED_NEEDS_REVIEW,
            BookRunStatus.PAUSED,
            BookRunStatus.CANCEL_REQUESTED,
            BookRunStatus.BUDGET_BLOCKED,
            BookRunStatus.FAILED,
        }
    ),
    BookRunStatus.GLOBAL_REVISION: frozenset(
        {
            BookRunStatus.GLOBAL_REVIEW,
            BookRunStatus.COMPLETED_NEEDS_REVIEW,
            BookRunStatus.PAUSED,
            BookRunStatus.CANCEL_REQUESTED,
            BookRunStatus.BUDGET_BLOCKED,
            BookRunStatus.FAILED,
        }
    ),
    BookRunStatus.BUDGET_BLOCKED: frozenset(
        {BookRunStatus.GENERATING, BookRunStatus.GLOBAL_REVIEW, BookRunStatus.CANCELLED}
    ),
    BookRunStatus.CANCEL_REQUESTED: frozenset({BookRunStatus.CANCELLED}),
    BookRunStatus.COMPLETED: frozenset(),
    BookRunStatus.COMPLETED_NEEDS_REVIEW: frozenset(),
    BookRunStatus.CANCELLED: frozenset(),
    BookRunStatus.FAILED: frozenset(),
}


TERMINAL_BOOK_RUN_STATUSES = frozenset(
    {
        BookRunStatus.COMPLETED,
        BookRunStatus.COMPLETED_NEEDS_REVIEW,
        BookRunStatus.CANCELLED,
        BookRunStatus.FAILED,
    }
)


def transition_book_run(
    run: BookRun, target: BookRunStatus, *, now: datetime | None = None
) -> None:
    """Apply one legal lifecycle transition and terminal timestamps."""
    if target is run.status:
        return
    if target not in _ALLOWED[run.status]:
        raise InvalidStateError(f"BookRun cannot transition from {run.status} to {target}")
    timestamp = now or utc_now()
    run.status = target
    run.updated_at = timestamp
    if run.started_at is None and target not in {BookRunStatus.PENDING, BookRunStatus.CANCELLED}:
        run.started_at = timestamp
    if target in TERMINAL_BOOK_RUN_STATUSES:
        run.finished_at = timestamp
