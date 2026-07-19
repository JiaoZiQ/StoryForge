"""Caller-owned persistence queries for full-book aggregates and analyses."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from storyforge.enums import BookRunStatus, BookSnapshotStatus
from storyforge.models import (
    BookEvaluation,
    BookRevisionPlan,
    BookRun,
    BookSnapshot,
    ChapterTransitionEvaluation,
    CharacterArcPoint,
    CharacterKnowledge,
    RelationshipHistory,
    TimelineEvent,
)
from storyforge.repositories.base import PageSlice, Repository

ACTIVE_BOOK_RUN_STATUSES = (
    BookRunStatus.PENDING,
    BookRunStatus.PLANNING_VALIDATION,
    BookRunStatus.GENERATING,
    BookRunStatus.PAUSED,
    BookRunStatus.GLOBAL_REVIEW,
    BookRunStatus.GLOBAL_REVISION,
    BookRunStatus.CANCEL_REQUESTED,
    BookRunStatus.BUDGET_BLOCKED,
)


class BookRunRepository(Repository[BookRun]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, BookRun)

    def get_for_update(self, run_id: int) -> BookRun | None:
        return self.session.scalar(select(BookRun).where(BookRun.id == run_id).with_for_update())

    def active_for_project(self, project_id: int) -> BookRun | None:
        return self.session.scalar(
            select(BookRun)
            .where(BookRun.project_id == project_id, BookRun.status.in_(ACTIVE_BOOK_RUN_STATUSES))
            .order_by(BookRun.id.desc())
            .limit(1)
        )

    def by_idempotency_key(self, key: str) -> BookRun | None:
        return self.session.scalar(select(BookRun).where(BookRun.idempotency_key == key))

    def page_for_project(self, project_id: int, *, page: int, page_size: int) -> PageSlice[BookRun]:
        return self.paginate(
            select(BookRun).where(BookRun.project_id == project_id).order_by(BookRun.id.desc()),
            page=page,
            page_size=page_size,
        )


class BookSnapshotRepository(Repository[BookSnapshot]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, BookSnapshot)

    def by_hash(self, run_id: int, content_hash: str) -> BookSnapshot | None:
        return self.session.scalar(
            select(BookSnapshot).where(
                BookSnapshot.book_run_id == run_id,
                BookSnapshot.content_hash == content_hash,
            )
        )

    def next_number(self, run_id: int) -> int:
        value = self.session.scalar(
            select(func.coalesce(func.max(BookSnapshot.snapshot_number), 0)).where(
                BookSnapshot.book_run_id == run_id
            )
        )
        return int(value or 0) + 1

    def list_for_project(self, project_id: int) -> list[BookSnapshot]:
        return list(
            self.session.scalars(
                select(BookSnapshot)
                .where(BookSnapshot.project_id == project_id)
                .order_by(BookSnapshot.id.desc())
            )
        )

    def accepted_for_project(self, project_id: int) -> BookSnapshot | None:
        return self.session.scalar(
            select(BookSnapshot)
            .where(
                BookSnapshot.project_id == project_id,
                BookSnapshot.status == BookSnapshotStatus.ACCEPTED,
            )
            .order_by(BookSnapshot.snapshot_number.desc())
            .limit(1)
        )


class TimelineEventRepository(Repository[TimelineEvent]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, TimelineEvent)

    def for_snapshot(self, snapshot_id: int) -> list[TimelineEvent]:
        return list(
            self.session.scalars(
                select(TimelineEvent)
                .where(TimelineEvent.book_snapshot_id == snapshot_id)
                .order_by(TimelineEvent.sequence_index, TimelineEvent.id)
            )
        )


class CharacterArcRepository(Repository[CharacterArcPoint]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, CharacterArcPoint)

    def for_snapshot(self, snapshot_id: int) -> list[CharacterArcPoint]:
        return list(
            self.session.scalars(
                select(CharacterArcPoint)
                .where(CharacterArcPoint.book_snapshot_id == snapshot_id)
                .order_by(CharacterArcPoint.character_id, CharacterArcPoint.chapter_number)
            )
        )


class CharacterKnowledgeRepository(Repository[CharacterKnowledge]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, CharacterKnowledge)

    def for_snapshot(self, snapshot_id: int) -> list[CharacterKnowledge]:
        return list(
            self.session.scalars(
                select(CharacterKnowledge)
                .where(CharacterKnowledge.book_snapshot_id == snapshot_id)
                .order_by(CharacterKnowledge.character_id, CharacterKnowledge.learned_chapter)
            )
        )


class RelationshipHistoryRepository(Repository[RelationshipHistory]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, RelationshipHistory)

    def for_snapshot(self, snapshot_id: int) -> list[RelationshipHistory]:
        return list(
            self.session.scalars(
                select(RelationshipHistory)
                .where(RelationshipHistory.book_snapshot_id == snapshot_id)
                .order_by(RelationshipHistory.chapter_number, RelationshipHistory.id)
            )
        )


class ChapterTransitionRepository(Repository[ChapterTransitionEvaluation]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ChapterTransitionEvaluation)

    def for_snapshot(self, snapshot_id: int) -> list[ChapterTransitionEvaluation]:
        return list(
            self.session.scalars(
                select(ChapterTransitionEvaluation)
                .where(ChapterTransitionEvaluation.book_snapshot_id == snapshot_id)
                .order_by(ChapterTransitionEvaluation.from_chapter)
            )
        )


class BookEvaluationRepository(Repository[BookEvaluation]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, BookEvaluation)

    def latest_for_snapshot(self, snapshot_id: int) -> BookEvaluation | None:
        return self.session.scalar(
            select(BookEvaluation)
            .where(BookEvaluation.book_snapshot_id == snapshot_id)
            .order_by(BookEvaluation.evaluation_version.desc())
            .limit(1)
        )

    def by_idempotency_key(self, key: str) -> BookEvaluation | None:
        return self.session.scalar(
            select(BookEvaluation).where(BookEvaluation.idempotency_key == key)
        )


class BookRevisionPlanRepository(Repository[BookRevisionPlan]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, BookRevisionPlan)

    def latest_for_snapshot(self, snapshot_id: int) -> BookRevisionPlan | None:
        return self.session.scalar(
            select(BookRevisionPlan)
            .where(BookRevisionPlan.book_snapshot_id == snapshot_id)
            .order_by(BookRevisionPlan.revision_round.desc())
            .limit(1)
        )
