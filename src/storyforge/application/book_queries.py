"""Content-free public projections for BookRuns, snapshots, and global analyses."""

from __future__ import annotations

from sqlalchemy import select

from storyforge.database import SessionFactory
from storyforge.exceptions import EntityNotFoundError
from storyforge.models import (
    BookSnapshot,
    Chapter,
    Character,
    Evaluation,
    Foreshadowing,
)
from storyforge.repositories import (
    BookEvaluationRepository,
    BookRevisionPlanRepository,
    BookSnapshotRepository,
    ChapterTransitionRepository,
    CharacterArcRepository,
    RelationshipHistoryRepository,
    TimelineEventRepository,
)
from storyforge.schemas.books import (
    BookAnalysisResponse,
    BookEvaluationResponse,
    BookRevisionPlanResponse,
    BookSnapshotPageResponse,
    BookSnapshotResponse,
    TimelinePageResponse,
)


class BookQueryApplicationService:
    """Keep Book HTTP routes free of direct ORM and full manuscript fields."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def snapshots(self, project_id: int) -> BookSnapshotPageResponse:
        with self._session_factory() as session:
            items = BookSnapshotRepository(session).list_for_project(project_id)
            return BookSnapshotPageResponse(
                items=[self._snapshot(item) for item in items], total_items=len(items)
            )

    def snapshot(self, snapshot_id: int) -> BookSnapshotResponse:
        with self._session_factory() as session:
            item = self._require_snapshot(session, snapshot_id)
            return self._snapshot(item)

    def evaluation(self, snapshot_id: int) -> BookEvaluationResponse:
        with self._session_factory() as session:
            self._require_snapshot(session, snapshot_id)
            item = BookEvaluationRepository(session).latest_for_snapshot(snapshot_id)
            if item is None:
                raise EntityNotFoundError("Book snapshot evaluation was not found")
            return BookEvaluationResponse(
                id=item.id,
                book_snapshot_id=item.book_snapshot_id,
                evaluation_version=item.evaluation_version,
                final_score=item.final_score,
                passed=item.passed,
                dimension_scores=item.dimension_scores,
                blocking_reasons=item.blocking_reasons,
                recommended_action=item.recommended_action,
                priority_chapters=item.priority_chapters,
                global_issues=item.global_issues,
                evaluator_versions=item.evaluator_versions,
                prompt_versions=item.prompt_versions,
                created_at=item.created_at,
            )

    def timeline(self, snapshot_id: int, *, page: int, page_size: int) -> TimelinePageResponse:
        with self._session_factory() as session:
            self._require_snapshot(session, snapshot_id)
            rows = TimelineEventRepository(session).for_snapshot(snapshot_id)
            total = len(rows)
            selected = rows[(page - 1) * page_size : page * page_size]
            items: list[dict[str, object]] = [
                {
                    "id": row.id,
                    "chapter_id": row.chapter_id,
                    "chapter_version_id": row.chapter_version_id,
                    "event_key": row.event_key,
                    "title": row.title,
                    "description": row.description,
                    "story_time": row.story_time,
                    "sequence_index": row.sequence_index,
                    "participant_entity_ids": row.participant_entity_ids,
                    "causes_event_ids": row.causes_event_ids,
                    "confidence": row.confidence,
                    "evidence": row.evidence,
                }
                for row in selected
            ]
        return TimelinePageResponse(
            items=items,
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=(total + page_size - 1) // page_size,
        )

    def character_arcs(self, snapshot_id: int) -> BookAnalysisResponse:
        with self._session_factory() as session:
            snapshot = self._require_snapshot(session, snapshot_id)
            rows = CharacterArcRepository(session).for_snapshot(snapshot_id)
            names = {
                item.id: item.name
                for item in session.scalars(
                    select(Character).where(Character.project_id == snapshot.project_id)
                )
            }
            items: list[dict[str, object]] = [
                {
                    "character_id": row.character_id,
                    "character_name": names.get(row.character_id, "unknown"),
                    "chapter_number": row.chapter_number,
                    "chapter_version_id": row.chapter_version_id,
                    "goals": row.goals,
                    "emotional_state": row.emotional_state,
                    "physical_state": row.physical_state,
                    "location": row.location,
                    "knowledge": row.knowledge,
                    "relationships": row.relationships,
                    "evidence": row.evidence,
                }
                for row in rows
            ]
            score = _summary_score(snapshot, "character_arcs")
        return BookAnalysisResponse(
            snapshot_id=snapshot_id,
            kind="character_arcs",
            score=score,
            summary={
                "point_count": len(items),
                "character_count": len({i["character_id"] for i in items}),
            },
            items=items,
        )

    def relationships(self, snapshot_id: int) -> BookAnalysisResponse:
        with self._session_factory() as session:
            self._require_snapshot(session, snapshot_id)
            rows = RelationshipHistoryRepository(session).for_snapshot(snapshot_id)
            items: list[dict[str, object]] = [
                {
                    "subject_character_id": row.subject_character_id,
                    "object_character_id": row.object_character_id,
                    "relationship_type": row.relationship_type,
                    "value": row.value,
                    "chapter_number": row.chapter_number,
                    "valid_from_chapter": row.valid_from_chapter,
                    "valid_to_chapter": row.valid_to_chapter,
                    "evidence": row.evidence,
                }
                for row in rows
            ]
        return BookAnalysisResponse(
            snapshot_id=snapshot_id,
            kind="relationships",
            summary={"change_count": len(items)},
            items=items,
        )

    def foreshadowing(self, snapshot_id: int) -> BookAnalysisResponse:
        with self._session_factory() as session:
            snapshot = self._require_snapshot(session, snapshot_id)
            rows = list(
                session.scalars(
                    select(Foreshadowing)
                    .where(Foreshadowing.project_id == snapshot.project_id)
                    .order_by(Foreshadowing.setup_chapter, Foreshadowing.id)
                )
            )
            items: list[dict[str, object]] = [
                {
                    "id": row.id,
                    "description": row.description,
                    "importance": row.importance,
                    "setup_chapter": row.setup_chapter,
                    "expected_payoff_chapter": row.expected_payoff_chapter,
                    "payoff_chapter": row.payoff_chapter,
                    "status": row.status.value,
                }
                for row in rows
            ]
            rate = float(snapshot.evaluation_summary.get("foreshadowing_payoff_rate", 0))
        return BookAnalysisResponse(
            snapshot_id=snapshot_id,
            kind="foreshadowing",
            score=round(rate * 10, 2),
            summary={"total": len(items), "payoff_rate": rate},
            items=items,
        )

    def pacing(self, snapshot_id: int) -> BookAnalysisResponse:
        with self._session_factory() as session:
            snapshot = self._require_snapshot(session, snapshot_id)
            mapping = snapshot.chapter_version_map
            items: list[dict[str, object]] = []
            for chapter in session.scalars(
                select(Chapter)
                .where(Chapter.project_id == snapshot.project_id)
                .order_by(Chapter.chapter_number)
            ):
                version_id = mapping.get(str(chapter.chapter_number))
                evaluation = session.scalar(
                    select(Evaluation)
                    .where(Evaluation.chapter_version_id == version_id)
                    .order_by(Evaluation.evaluation_version.desc())
                    .limit(1)
                )
                items.append(
                    {
                        "chapter_number": chapter.chapter_number,
                        "word_count": (
                            chapter.accepted_version.word_count
                            if chapter.accepted_version is not None
                            and chapter.accepted_version.id == version_id
                            else 0
                        ),
                        "dialogue_ratio": (
                            evaluation.mechanical_metrics.get("dialogue_ratio", 0)
                            if evaluation is not None
                            else 0
                        ),
                        "chapter_score": evaluation.overall_score if evaluation is not None else 0,
                        "pacing_score": evaluation.pacing_score if evaluation is not None else 0,
                    }
                )
            score = float(snapshot.evaluation_summary.get("pacing_score", 0))
        return BookAnalysisResponse(
            snapshot_id=snapshot_id,
            kind="pacing",
            score=score,
            summary={"chapter_count": len(items)},
            items=items,
        )

    def transitions(self, snapshot_id: int) -> BookAnalysisResponse:
        with self._session_factory() as session:
            self._require_snapshot(session, snapshot_id)
            rows = ChapterTransitionRepository(session).for_snapshot(snapshot_id)
            items: list[dict[str, object]] = [
                {
                    "from_chapter": row.from_chapter,
                    "to_chapter": row.to_chapter,
                    "score": row.score,
                    "issues": row.issues,
                    "strengths": row.strengths,
                }
                for row in rows
            ]
        average = sum(row.score for row in rows) / len(rows) if rows else 10
        return BookAnalysisResponse(
            snapshot_id=snapshot_id,
            kind="transitions",
            score=round(average, 2),
            summary={"transition_count": len(items)},
            items=items,
        )

    def revision_plan(self, snapshot_id: int) -> BookRevisionPlanResponse:
        with self._session_factory() as session:
            self._require_snapshot(session, snapshot_id)
            plan = BookRevisionPlanRepository(session).latest_for_snapshot(snapshot_id)
            if plan is None:
                raise EntityNotFoundError("Book revision plan was not found")
            return BookRevisionPlanResponse(
                id=plan.id,
                book_snapshot_id=plan.book_snapshot_id,
                revision_round=plan.revision_round,
                global_objectives=plan.global_objectives,
                dependency_order=plan.dependency_order,
                must_preserve=plan.must_preserve,
                global_constraints=plan.global_constraints,
                estimated_calls=plan.estimated_calls,
                estimated_tokens=plan.estimated_tokens,
                estimated_cost=plan.estimated_cost,
                status=plan.status.value,
                tasks=[
                    {
                        "chapter_number": item.chapter_number,
                        "priority": item.priority,
                        "issue_codes": item.issue_codes,
                        "objective": item.objective,
                        "required_changes": item.required_changes,
                        "affected_future_chapters": item.affected_future_chapters,
                        "rerun_global_checks": item.rerun_global_checks,
                        "status": item.status.value,
                    }
                    for item in plan.tasks
                ],
            )

    @staticmethod
    def _require_snapshot(session: object, snapshot_id: int) -> BookSnapshot:
        from sqlalchemy.orm import Session

        if not isinstance(session, Session):
            raise TypeError("Snapshot query requires a SQLAlchemy session")
        item = BookSnapshotRepository(session).get(snapshot_id)
        if item is None:
            raise EntityNotFoundError(f"Book snapshot {snapshot_id} was not found")
        return item

    @staticmethod
    def _snapshot(item: BookSnapshot) -> BookSnapshotResponse:
        return BookSnapshotResponse(
            id=item.id,
            project_id=item.project_id,
            book_run_id=item.book_run_id,
            snapshot_number=item.snapshot_number,
            status=item.status,
            chapter_version_map=item.chapter_version_map,
            total_words=item.total_words,
            chapter_count=item.chapter_count,
            accepted_chapter_count=item.accepted_chapter_count,
            content_hash=item.content_hash,
            evaluation_summary=item.evaluation_summary,
            created_at=item.created_at,
            accepted_at=item.accepted_at,
        )


def _summary_score(snapshot: BookSnapshot, key: str) -> float | None:
    evaluation_id = snapshot.evaluation_summary.get("evaluation_id")
    if not isinstance(evaluation_id, int):
        return None
    # Character score is included in the global dimension response, not duplicated on Snapshot.
    return None
