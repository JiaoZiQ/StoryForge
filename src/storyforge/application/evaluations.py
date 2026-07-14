"""Evaluation, conflict, and accepted-fact query use cases."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from storyforge.database import SessionFactory
from storyforge.enums import ConflictSeverity, ConflictStatus, ConflictType, FactStatus
from storyforge.evaluation.models import ChapterEvaluationRequest
from storyforge.exceptions import DomainValidationError, EntityNotFoundError, InvalidStateError
from storyforge.models import Chapter, Conflict, Evaluation, EvaluationIssue, Fact
from storyforge.repositories import (
    ChapterRepository,
    ConflictRepository,
    EvaluationIssueRepository,
    EvaluationRepository,
    FactRepository,
    ProjectRepository,
)
from storyforge.schemas.api import (
    ConflictPatchRequest,
    ConflictResponse,
    EvaluateChapterRequest,
    EvaluationDetail,
    EvaluationIssueResponse,
    EvaluationSummary,
    FactResponse,
    PageResponse,
)

from .common import page_response
from .factory import DomainServiceFactory


class EvaluationApplicationService:
    """Read immutable evaluations and manage explicitly mutable conflicts."""

    def __init__(
        self, session_factory: SessionFactory, factory: DomainServiceFactory | None = None
    ) -> None:
        self._session_factory = session_factory
        self._factory = factory

    def evaluate(
        self, project_id: int, chapter_number: int, request: EvaluateChapterRequest
    ) -> EvaluationDetail:
        if self._factory is None:
            raise InvalidStateError("Evaluation provider factory is unavailable")
        chapter_version_id: int | None = None
        with self._session_factory() as session:
            chapter = self._require_chapter(session, project_id, chapter_number)
            chapter_version_id = chapter.current_version_id
            if chapter_version_id is None:
                raise InvalidStateError("Chapter has no concrete version to evaluate")
            if not request.force_new_version:
                existing = EvaluationRepository(session).latest_for_version(chapter_version_id)
                if existing is not None:
                    issues = EvaluationIssueRepository(session).list_for_evaluation(existing.id)
                    return _evaluation_detail(existing, issues)
        with self._factory.provider(
            "evaluation",
            project_id=project_id,
            chapter_number=chapter_number,
            override=request.provider,
        ) as provider:
            result = self._factory.evaluation_service(provider).evaluate(
                ChapterEvaluationRequest(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    chapter_version_id=chapter_version_id,
                )
            )
        return self.get_evaluation(project_id, chapter_number, result.evaluation_id)

    def list_evaluations(
        self,
        project_id: int,
        chapter_number: int,
        *,
        page: int,
        page_size: int,
        version_id: int | None = None,
        passed: bool | None = None,
        recommended_action: str | None = None,
        min_score: float | None = None,
        max_score: float | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> PageResponse[EvaluationSummary]:
        with self._session_factory() as session:
            chapter = self._require_chapter(session, project_id, chapter_number)
            result = EvaluationRepository(session).page_for_chapter(
                chapter.id,
                page=page,
                page_size=page_size,
                version_id=version_id,
                passed=passed,
                recommended_action=recommended_action,
                min_score=min_score,
                max_score=max_score,
                sort=sort,
                order=order,
            )
            items = [_evaluation_summary(item) for item in result.items]
        return page_response(result, page=page, page_size=page_size, items=items)

    def get_evaluation(
        self, project_id: int, chapter_number: int, evaluation_id: int
    ) -> EvaluationDetail:
        with self._session_factory() as session:
            chapter = self._require_chapter(session, project_id, chapter_number)
            evaluation = EvaluationRepository(session).get(evaluation_id)
            if evaluation is None or evaluation.chapter_id != chapter.id:
                raise EntityNotFoundError(f"Evaluation {evaluation_id} was not found")
            issues = EvaluationIssueRepository(session).list_for_evaluation(evaluation.id)
            return _evaluation_detail(evaluation, issues)

    def list_conflicts(
        self,
        project_id: int,
        *,
        page: int,
        page_size: int,
        chapter_number: int | None = None,
        version_id: int | None = None,
        severity: ConflictSeverity | None = None,
        conflict_type: ConflictType | None = None,
        status: ConflictStatus | None = None,
        rule_code: str | None = None,
    ) -> PageResponse[ConflictResponse]:
        with self._session_factory() as session:
            self._require_project(session, project_id)
            result = ConflictRepository(session).page_for_project(
                project_id,
                page=page,
                page_size=page_size,
                chapter_number=chapter_number,
                version_id=version_id,
                severity=severity,
                conflict_type=conflict_type,
                status=status,
                rule_code=rule_code,
            )
            items = [_conflict(item) for item in result.items]
        return page_response(result, page=page, page_size=page_size, items=items)

    def get_conflict(self, project_id: int, conflict_id: int) -> ConflictResponse:
        with self._session_factory() as session:
            conflict = ConflictRepository(session).get(conflict_id)
            if conflict is None or conflict.project_id != project_id:
                raise EntityNotFoundError(f"Conflict {conflict_id} was not found")
            return _conflict(conflict)

    def update_conflict(
        self, project_id: int, conflict_id: int, request: ConflictPatchRequest
    ) -> ConflictResponse:
        with self._session_factory.begin() as session:
            conflict = ConflictRepository(session).get(conflict_id)
            if conflict is None or conflict.project_id != project_id:
                raise EntityNotFoundError(f"Conflict {conflict_id} was not found")
            self._validate_conflict_transition(conflict.status, request.status)
            conflict.status = request.status
            conflict.resolution_note = request.resolution_note
            conflict.resolved_at = (
                None if request.status is ConflictStatus.OPEN else datetime.now(UTC)
            )
            session.flush()
        return self.get_conflict(project_id, conflict_id)

    def list_facts(
        self,
        project_id: int,
        *,
        page: int,
        page_size: int,
        chapter_number: int | None = None,
        subject: str | None = None,
        predicate: str | None = None,
        status: FactStatus = FactStatus.ACCEPTED,
        version_id: int | None = None,
        valid_at_chapter: int | None = None,
        confidence_min: float | None = None,
    ) -> PageResponse[FactResponse]:
        self._validate_public_fact_status(status)
        with self._session_factory() as session:
            self._require_project(session, project_id)
            result = FactRepository(session).page_for_project(
                project_id,
                page=page,
                page_size=page_size,
                chapter_number=chapter_number,
                subject=subject,
                predicate=predicate,
                status=status,
                version_id=version_id,
                valid_at_chapter=valid_at_chapter,
                confidence_min=confidence_min,
            )
            items = [_fact(item) for item in result.items]
        return page_response(result, page=page, page_size=page_size, items=items)

    def get_fact(self, project_id: int, fact_id: int) -> FactResponse:
        with self._session_factory() as session:
            fact = FactRepository(session).get(fact_id)
            if (
                fact is None
                or fact.project_id != project_id
                or fact.status is not FactStatus.ACCEPTED
            ):
                raise EntityNotFoundError(f"Accepted fact {fact_id} was not found")
            return _fact(fact)

    @staticmethod
    def _validate_public_fact_status(status: FactStatus) -> None:
        if status is not FactStatus.ACCEPTED:
            raise DomainValidationError("The public API exposes accepted facts only")

    @staticmethod
    def _validate_conflict_transition(current: ConflictStatus, requested: ConflictStatus) -> None:
        if (
            current is requested
            or current is ConflictStatus.OPEN
            or requested is ConflictStatus.OPEN
        ):
            return
        raise InvalidStateError(
            f"Conflict cannot transition directly from {current.value} to {requested.value}"
        )

    @staticmethod
    def _require_project(session: Session, project_id: int) -> None:
        if ProjectRepository(session).get(project_id) is None:
            raise EntityNotFoundError(f"Project {project_id} was not found")

    @staticmethod
    def _require_chapter(session: Session, project_id: int, chapter_number: int) -> Chapter:
        chapter = ChapterRepository(session).get_by_number(project_id, chapter_number)
        if chapter is None:
            raise EntityNotFoundError(
                f"Chapter {chapter_number} was not found for project {project_id}"
            )
        return chapter


def _evaluation_summary(evaluation: Evaluation) -> EvaluationSummary:
    return EvaluationSummary(
        id=evaluation.id,
        evaluation_version=evaluation.evaluation_version,
        chapter_version_id=evaluation.chapter_version_id,
        status=evaluation.status,
        mechanical_score=evaluation.mechanical_score,
        critic_score=evaluation.critic_score,
        consistency_score=evaluation.consistency_score,
        final_score=evaluation.overall_score,
        passed=evaluation.passed,
        recommended_action=evaluation.recommended_action,
        created_at=evaluation.created_at,
    )


def _evaluation_detail(evaluation: Evaluation, issues: list[EvaluationIssue]) -> EvaluationDetail:
    return EvaluationDetail(
        **_evaluation_summary(evaluation).model_dump(),
        raw_scores=dict(evaluation.raw_scores),
        weighted_scores=dict(evaluation.weighted_scores),
        mechanical_metrics=dict(evaluation.mechanical_metrics),
        critic_dimensions=dict(evaluation.critic_dimensions),
        blocking_reasons=list(evaluation.blocking_reasons),
        issues=[
            EvaluationIssueResponse(
                id=item.id,
                source=item.source,
                code=item.code,
                category=item.category,
                severity=item.severity,
                description=item.description,
                evidence=item.evidence,
                suggestion=item.suggestion,
                score_penalty=item.score_penalty,
                details=dict(item.details),
            )
            for item in issues
        ],
        evaluator_versions=dict(evaluation.evaluator_versions),
        prompt_versions=dict(evaluation.prompt_versions),
        provider=evaluation.provider,
        model=evaluation.model,
    )


def _conflict(conflict: Conflict) -> ConflictResponse:
    return ConflictResponse.model_validate(conflict, from_attributes=True)


def _fact(fact: Fact) -> FactResponse:
    return FactResponse(
        id=fact.id,
        project_id=fact.project_id,
        chapter_id=fact.chapter_id,
        chapter_number=fact.chapter.chapter_number,
        chapter_version_id=fact.chapter_version_id,
        subject=fact.subject,
        predicate=fact.predicate,
        object=fact.object,
        fact_type=fact.fact_type,
        valid_from_chapter=fact.valid_from_chapter,
        valid_to_chapter=fact.valid_to_chapter,
        confidence=fact.confidence,
        source_quote=fact.source_quote,
        status=fact.status,
    )
