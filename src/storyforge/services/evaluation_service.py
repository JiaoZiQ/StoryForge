"""Versioned chapter evaluation orchestration and persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from storyforge.agents import CriticAgent
from storyforge.consistency import ConsistencyChecker
from storyforge.consistency.models import (
    ChapterOutlineEvidence,
    ChapterSummaryEvidence,
    CharacterEvidence,
    ConsistencyCheckRequest,
    ConsistencyCheckResult,
    FactEvidence,
    ForeshadowingEvidence,
    ForeshadowingUpdateEvidence,
    StoryRuleEvidence,
)
from storyforge.database import SessionFactory
from storyforge.enums import (
    ChapterStatus,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    EvaluationStatus,
    ForeshadowingStatus,
)
from storyforge.evaluation import EvaluationScorer, MechanicalEvaluator
from storyforge.evaluation.models import (
    ChapterCritique,
    ChapterEvaluationRequest,
    ChapterEvaluationResult,
    CombinedEvaluationResult,
    CriticCharacterContext,
    CriticContext,
    MechanicalEvaluationRequest,
    MechanicalEvaluationResult,
    RecommendedAction,
)
from storyforge.exceptions import (
    AgentExecutionError,
    EntityNotFoundError,
    EvaluationError,
    InvalidStateError,
)
from storyforge.models import (
    Chapter,
    Conflict,
    Evaluation,
    EvaluationIssue,
    Fact,
    Foreshadowing,
)
from storyforge.repositories import (
    ChapterRepository,
    CharacterRepository,
    ConflictRepository,
    EvaluationIssueRepository,
    EvaluationRepository,
    FactRepository,
    ProjectRepository,
    StoryRuleRepository,
)

logger = logging.getLogger(__name__)

_EVALUATABLE_STATUSES = {
    ChapterStatus.GENERATED,
    ChapterStatus.EVALUATED_PASSED,
    ChapterStatus.EVALUATED_NEEDS_REVISION,
    ChapterStatus.EVALUATION_FAILED,
    ChapterStatus.ACCEPTED,
    ChapterStatus.NEEDS_REVISION,
}


@dataclass(frozen=True, slots=True)
class _LoadedEvaluationContext:
    project_id: int
    chapter_id: int
    chapter_number: int
    target_words: int
    language: str
    genre: str
    premise: str
    content: str
    summary: str
    previous_status: ChapterStatus
    consistency_request: ConsistencyCheckRequest
    critic_characters: list[CriticCharacterContext]
    story_rule_statements: list[str]
    active_foreshadowing_descriptions: list[str]
    previous_chapter_summary: str | None
    outline_metadata: dict[str, object]


class EvaluationService:
    """Run local and LLM evaluation, then save one immutable attempt."""

    def __init__(
        self,
        session_factory: SessionFactory,
        mechanical_evaluator: MechanicalEvaluator,
        consistency_checker: ConsistencyChecker,
        critic: CriticAgent,
        scorer: EvaluationScorer,
    ) -> None:
        self._session_factory = session_factory
        self._mechanical = mechanical_evaluator
        self._consistency = consistency_checker
        self._critic = critic
        self._scorer = scorer

    def evaluate(self, request: ChapterEvaluationRequest) -> ChapterEvaluationResult:
        """Evaluate one fact-extracted chapter without replacing prior attempts."""
        loaded = self._load_context(request)
        self._mark_evaluating(loaded)
        try:
            mechanical = self._mechanical.evaluate(
                MechanicalEvaluationRequest(
                    chapter_id=loaded.chapter_id,
                    chapter_number=loaded.chapter_number,
                    content=loaded.content,
                    target_words=loaded.target_words,
                    language=loaded.language,
                )
            )
            consistency = self._consistency.check(loaded.consistency_request)
        except Exception as exc:
            self._mark_failed(loaded)
            raise EvaluationError("Local chapter evaluation failed") from exc

        critic_context = self._build_critic_context(loaded, mechanical, consistency)
        try:
            critic_result = self._critic.critique(critic_context)
        except (AgentExecutionError, EvaluationError) as exc:
            try:
                self._persist_partial(loaded, mechanical, consistency)
            except SQLAlchemyError as persistence_error:
                self._mark_failed(loaded)
                raise EvaluationError("Evaluation persistence failed") from persistence_error
            logger.warning(
                "Critic evaluation failed; local results preserved project_id=%s chapter_id=%s",
                loaded.project_id,
                loaded.chapter_id,
            )
            raise EvaluationError(
                "CriticAgent failed; local evaluation results were preserved"
            ) from exc

        combined = self._scorer.combine(
            mechanical_score=mechanical.score,
            critique=critic_result.output,
            consistency_score=consistency.score,
            critical_conflicts=consistency.critical_count,
            high_conflicts=consistency.high_count,
            content_empty=not loaded.content.strip(),
        )
        try:
            result = self._persist_complete(
                loaded,
                mechanical,
                consistency,
                critic_result.output,
                combined,
                provider=critic_result.provider,
                model=critic_result.model,
                prompt_versions=critic_result.prompt_versions,
            )
        except SQLAlchemyError as exc:
            self._mark_failed(loaded)
            raise EvaluationError("Evaluation persistence failed") from exc
        logger.info(
            "Chapter evaluation completed project_id=%s chapter_id=%s version=%s score=%.2f passed=%s",
            result.project_id,
            result.chapter_id,
            result.evaluation_version,
            result.final_score,
            result.passed,
        )
        return result

    def list_evaluations(
        self, project_id: int, chapter_number: int
    ) -> list[ChapterEvaluationResult]:
        """Return immutable evaluation history for one chapter."""
        with self._session_factory() as session:
            chapter = ChapterRepository(session).get_by_number(project_id, chapter_number)
            if chapter is None:
                raise EntityNotFoundError("Project chapter was not found")
            return [
                self._to_result(item, chapter.chapter_number)
                for item in EvaluationRepository(session).list_for_chapter(chapter.id)
            ]

    def list_conflicts(
        self,
        project_id: int,
        *,
        chapter_number: int | None = None,
        severity: ConflictSeverity | None = None,
        conflict_type: ConflictType | None = None,
        status: ConflictStatus | None = None,
    ) -> list[Conflict]:
        """Return filtered conflicts while keeping transaction handling internal."""
        with self._session_factory() as session:
            if ProjectRepository(session).get(project_id) is None:
                raise EntityNotFoundError(f"Project {project_id} was not found")
            chapter_id = None
            if chapter_number is not None:
                chapter = ChapterRepository(session).get_by_number(project_id, chapter_number)
                if chapter is None:
                    raise EntityNotFoundError("Project chapter was not found")
                chapter_id = chapter.id
            conflicts = ConflictRepository(session).list_for_project(
                project_id,
                chapter_id=chapter_id,
                severity=severity,
                conflict_type=conflict_type,
                status=status,
            )
            session.expunge_all()
            return conflicts

    def update_conflict_status(
        self, project_id: int, conflict_id: int, status: ConflictStatus
    ) -> Conflict:
        """Update only the human-managed conflict status and resolution timestamp."""
        with self._session_factory.begin() as session:
            conflict = ConflictRepository(session).get(conflict_id)
            if conflict is None or conflict.project_id != project_id:
                raise EntityNotFoundError(f"Conflict {conflict_id} was not found")
            conflict.status = status
            conflict.resolved_at = None if status is ConflictStatus.OPEN else datetime.now(UTC)
            session.flush()
            session.expunge(conflict)
        return conflict

    def _load_context(self, request: ChapterEvaluationRequest) -> _LoadedEvaluationContext:
        with self._session_factory() as session:
            project = ProjectRepository(session).get(request.project_id)
            chapter = ChapterRepository(session).get_by_number(
                request.project_id, request.chapter_number
            )
            if project is None or chapter is None:
                raise EntityNotFoundError("Project chapter was not found")
            if not chapter.content.strip():
                raise InvalidStateError("Only chapters with generated content can be evaluated")
            if chapter.status not in _EVALUATABLE_STATUSES:
                if chapter.status is ChapterStatus.FACT_EXTRACTION_FAILED:
                    raise InvalidStateError("Fact extraction must succeed before evaluation")
                raise InvalidStateError(f"Chapter cannot be evaluated from status {chapter.status}")

            current_facts = list(
                session.scalars(select(Fact).where(Fact.chapter_id == chapter.id).order_by(Fact.id))
            )
            historical_facts = FactRepository(session).list_known_before(
                project.id, chapter.chapter_number
            )
            characters = CharacterRepository(session).list_for_project(project.id)
            rules = StoryRuleRepository(session).list_active_for_project(project.id)
            foreshadowings = list(
                session.scalars(
                    select(Foreshadowing)
                    .where(
                        Foreshadowing.project_id == project.id,
                        Foreshadowing.setup_chapter <= chapter.chapter_number,
                    )
                    .order_by(Foreshadowing.id)
                )
            )
            earlier_chapters = list(
                session.scalars(
                    select(Chapter)
                    .where(
                        Chapter.project_id == project.id,
                        Chapter.chapter_number < chapter.chapter_number,
                    )
                    .order_by(Chapter.chapter_number)
                )
            )
            outline = _outline(chapter.outline_metadata)
            fact_evidence = [_fact_evidence(item, chapter.chapter_number) for item in current_facts]
            historical_evidence = [
                _fact_evidence(item, item.chapter.chapter_number) for item in historical_facts
            ]
            character_evidence = [
                CharacterEvidence(
                    name=item.name,
                    current_state=item.current_state,
                    knowledge=list(item.knowledge),
                    secrets=list(item.secrets),
                )
                for item in characters
            ]
            consistency_request = ConsistencyCheckRequest(
                project_id=project.id,
                chapter_id=chapter.id,
                chapter_number=chapter.chapter_number,
                content=chapter.content,
                new_facts=fact_evidence,
                historical_facts=historical_evidence,
                characters=character_evidence,
                story_rules=[
                    StoryRuleEvidence(
                        rule_id=item.id,
                        category=item.category,
                        statement=item.statement,
                        structured_metadata=dict(item.structured_metadata),
                    )
                    for item in rules
                ],
                outline=outline,
                active_foreshadowing=[
                    ForeshadowingEvidence(
                        foreshadowing_id=item.id,
                        description=item.description,
                        setup_chapter=item.setup_chapter,
                        expected_payoff_chapter=item.expected_payoff_chapter,
                        payoff_chapter=item.payoff_chapter,
                        status=item.status,
                    )
                    for item in foreshadowings
                ],
                foreshadowing_updates=[
                    ForeshadowingUpdateEvidence(
                        action="resolve",
                        description=item.description,
                        foreshadowing_id=item.id,
                        confidence=1,
                    )
                    for item in foreshadowings
                    if item.payoff_chapter == chapter.chapter_number
                    and item.status is ForeshadowingStatus.RESOLVED
                ],
                previous_summaries=[
                    ChapterSummaryEvidence(
                        chapter_number=item.chapter_number,
                        summary=item.summary or "",
                    )
                    for item in earlier_chapters
                    if item.summary
                ],
            )
            critic_characters = [
                CriticCharacterContext(
                    name=item.name,
                    role=item.role,
                    description=item.description,
                    current_state=item.current_state,
                )
                for item in characters
                if item.name
                in _string_list(chapter.outline_metadata.get("participating_characters", []))
            ]
            return _LoadedEvaluationContext(
                project_id=project.id,
                chapter_id=chapter.id,
                chapter_number=chapter.chapter_number,
                target_words=project.target_words_per_chapter,
                language=project.language,
                genre=project.genre,
                premise=project.premise,
                content=chapter.content,
                summary=chapter.summary or "",
                previous_status=chapter.status,
                consistency_request=consistency_request,
                critic_characters=critic_characters,
                story_rule_statements=[item.statement for item in rules],
                active_foreshadowing_descriptions=[item.description for item in foreshadowings],
                previous_chapter_summary=(
                    earlier_chapters[-1].summary if earlier_chapters else None
                ),
                outline_metadata=dict(chapter.outline_metadata),
            )

    def _mark_evaluating(self, loaded: _LoadedEvaluationContext) -> None:
        with self._session_factory.begin() as session:
            chapter = ChapterRepository(session).get(loaded.chapter_id)
            if chapter is None:
                raise EntityNotFoundError("Chapter disappeared before evaluation")
            if chapter.status is not loaded.previous_status:
                raise InvalidStateError("Chapter status changed before evaluation")
            chapter.status = ChapterStatus.EVALUATING

    def _mark_failed(self, loaded: _LoadedEvaluationContext) -> None:
        try:
            with self._session_factory.begin() as session:
                chapter = ChapterRepository(session).get(loaded.chapter_id)
                if chapter is not None and chapter.status is ChapterStatus.EVALUATING:
                    chapter.status = ChapterStatus.EVALUATION_FAILED
        except SQLAlchemyError:
            logger.exception(
                "Unable to persist evaluation failure state project_id=%s chapter_id=%s",
                loaded.project_id,
                loaded.chapter_id,
            )

    def _build_critic_context(
        self,
        loaded: _LoadedEvaluationContext,
        mechanical: MechanicalEvaluationResult,
        consistency: ConsistencyCheckResult,
    ) -> CriticContext:
        return CriticContext(
            project_id=loaded.project_id,
            chapter_id=loaded.chapter_id,
            chapter_number=loaded.chapter_number,
            genre=loaded.genre,
            premise=loaded.premise,
            outline=loaded.outline_metadata,
            content=loaded.content,
            summary=loaded.summary,
            characters=loaded.critic_characters,
            story_rules=loaded.story_rule_statements,
            previous_chapter_summary=loaded.previous_chapter_summary,
            active_foreshadowing=loaded.active_foreshadowing_descriptions,
            mechanical_summary={
                "score": mechanical.score,
                "metrics": mechanical.metrics.model_dump(mode="json"),
                "issue_codes": [item.code for item in mechanical.issues],
            },
            consistency_summary={
                "score": consistency.score,
                "conflicts": [
                    {
                        "code": item.rule_code,
                        "severity": item.severity,
                        "description": item.description,
                    }
                    for item in consistency.conflicts
                ],
            },
        )

    def _persist_complete(
        self,
        loaded: _LoadedEvaluationContext,
        mechanical: MechanicalEvaluationResult,
        consistency: ConsistencyCheckResult,
        critique: ChapterCritique,
        combined: CombinedEvaluationResult,
        *,
        provider: str,
        model: str,
        prompt_versions: dict[str, str],
    ) -> ChapterEvaluationResult:
        with self._session_factory.begin() as session:
            chapter = ChapterRepository(session).get(loaded.chapter_id)
            if chapter is None or chapter.status is not ChapterStatus.EVALUATING:
                raise InvalidStateError("Chapter is not in the evaluating state")
            repository = EvaluationRepository(session)
            evaluation = repository.add(
                Evaluation(
                    project_id=loaded.project_id,
                    chapter_id=loaded.chapter_id,
                    evaluator="milestone-4",
                    evaluation_version=repository.next_version(loaded.chapter_id),
                    status=EvaluationStatus.COMPLETED,
                    overall_score=combined.final_score,
                    mechanical_score=mechanical.score,
                    critic_score=critique.overall_score,
                    consistency_score=consistency.score,
                    prose_score=critique.prose.score,
                    character_score=critique.character.score,
                    plot_score=critique.plot.score,
                    pacing_score=critique.pacing.score,
                    dialogue_score=critique.dialogue.score,
                    emotional_impact_score=critique.emotional_impact.score,
                    outline_adherence_score=critique.outline_adherence.score,
                    raw_scores=combined.raw_scores,
                    weighted_scores=combined.weighted_scores,
                    evaluator_versions={
                        "mechanical": mechanical.evaluator_version,
                        "consistency": consistency.checker_version,
                        "scoring": self._scorer.config.version,
                    },
                    prompt_versions=prompt_versions,
                    blocking_reasons=combined.blocking_reasons,
                    recommended_action=combined.recommended_action,
                    passed=combined.passed,
                    provider=provider,
                    model=model,
                    config_version=self._scorer.config.version,
                    issues=_legacy_issues(mechanical, critique),
                    suggestions=[item.suggestion for item in critique.issues],
                )
            )
            self._add_issues(session, evaluation.id, mechanical, critique)
            self._add_conflicts(session, evaluation.id, loaded, consistency)
            session.flush()
            session.expire(evaluation, ["issue_records", "conflicts"])
            chapter.score = combined.final_score
            chapter.status = (
                ChapterStatus.EVALUATED_PASSED
                if combined.passed
                else ChapterStatus.EVALUATED_NEEDS_REVISION
            )
            result = self._to_result(evaluation, loaded.chapter_number)
        return result

    def _persist_partial(
        self,
        loaded: _LoadedEvaluationContext,
        mechanical: MechanicalEvaluationResult,
        consistency: ConsistencyCheckResult,
    ) -> None:
        with self._session_factory.begin() as session:
            chapter = ChapterRepository(session).get(loaded.chapter_id)
            if chapter is None or chapter.status is not ChapterStatus.EVALUATING:
                raise InvalidStateError("Chapter is not in the evaluating state")
            repository = EvaluationRepository(session)
            evaluation = repository.add(
                Evaluation(
                    project_id=loaded.project_id,
                    chapter_id=loaded.chapter_id,
                    evaluator="milestone-4",
                    evaluation_version=repository.next_version(loaded.chapter_id),
                    status=EvaluationStatus.PARTIAL_FAILED,
                    overall_score=0,
                    mechanical_score=mechanical.score,
                    critic_score=0,
                    consistency_score=consistency.score,
                    prose_score=0,
                    character_score=0,
                    plot_score=0,
                    raw_scores={
                        "mechanical": mechanical.score,
                        "consistency": consistency.score,
                    },
                    weighted_scores={},
                    evaluator_versions={
                        "mechanical": mechanical.evaluator_version,
                        "consistency": consistency.checker_version,
                        "scoring": self._scorer.config.version,
                    },
                    prompt_versions=self._critic.prompt_versions(),
                    blocking_reasons=["critic_agent_failed"],
                    recommended_action="human_review",
                    passed=False,
                    provider=self._critic.provider_name,
                    model="unavailable",
                    config_version=self._scorer.config.version,
                    issues=_legacy_issues(mechanical, None),
                )
            )
            self._add_issues(session, evaluation.id, mechanical, None)
            self._add_conflicts(session, evaluation.id, loaded, consistency)
            chapter.status = ChapterStatus.EVALUATION_FAILED

    @staticmethod
    def _add_issues(
        session: Session,
        evaluation_id: int,
        mechanical: MechanicalEvaluationResult,
        critique: ChapterCritique | None,
    ) -> None:
        EvaluationIssueRepository(session).add_many(
            EvaluationIssue(
                evaluation_id=evaluation_id,
                source="mechanical",
                code=item.code,
                category=item.category,
                severity=item.severity,
                description=item.message,
                evidence=item.evidence,
                score_penalty=item.score_penalty,
                details={"location": item.location},
            )
            for item in mechanical.issues
        )
        if critique is not None:
            EvaluationIssueRepository(session).add_many(
                EvaluationIssue(
                    evaluation_id=evaluation_id,
                    source="critic",
                    code=item.code,
                    category=item.category,
                    severity=item.severity,
                    description=item.description,
                    evidence=item.evidence,
                    suggestion=item.suggestion,
                    details={
                        "affected_characters": item.affected_characters,
                        "affected_facts": item.affected_facts,
                    },
                )
                for item in critique.issues
            )

    @staticmethod
    def _add_conflicts(
        session: Session,
        evaluation_id: int,
        loaded: _LoadedEvaluationContext,
        consistency: ConsistencyCheckResult,
    ) -> None:
        ConflictRepository(session).add_many(
            Conflict(
                evaluation_id=evaluation_id,
                project_id=loaded.project_id,
                chapter_id=loaded.chapter_id,
                conflict_type=item.conflict_type,
                severity=item.severity,
                subject=item.subject,
                description=item.description,
                new_evidence=item.new_evidence,
                existing_evidence=item.existing_evidence,
                existing_fact_id=item.existing_fact_id,
                suggested_resolution=item.suggested_resolution,
                confidence=item.confidence,
                rule_code=item.rule_code,
                status=ConflictStatus.OPEN,
            )
            for item in consistency.conflicts
        )

    @staticmethod
    def _to_result(evaluation: Evaluation, chapter_number: int) -> ChapterEvaluationResult:
        return ChapterEvaluationResult(
            evaluation_id=evaluation.id,
            project_id=evaluation.project_id,
            chapter_id=evaluation.chapter_id,
            chapter_number=chapter_number,
            evaluation_version=evaluation.evaluation_version,
            status=evaluation.status,
            mechanical_score=evaluation.mechanical_score,
            critic_score=evaluation.critic_score,
            consistency_score=evaluation.consistency_score,
            final_score=evaluation.overall_score,
            passed=evaluation.passed,
            issue_count=len(evaluation.issue_records),
            conflict_count=len(evaluation.conflicts),
            critical_conflict_count=sum(
                item.severity is ConflictSeverity.CRITICAL for item in evaluation.conflicts
            ),
            recommended_action=cast(RecommendedAction, evaluation.recommended_action),
            blocking_reasons=list(evaluation.blocking_reasons),
            evaluator_versions=dict(evaluation.evaluator_versions),
            prompt_versions=dict(evaluation.prompt_versions),
        )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _outline(metadata: dict[str, Any]) -> ChapterOutlineEvidence:
    return ChapterOutlineEvidence(
        key_events=_string_list(metadata.get("key_events", [])),
        forbidden_reveals=_string_list(metadata.get("forbidden_reveals", [])),
        payoff_foreshadowing=_string_list(metadata.get("payoff_foreshadowing", [])),
    )


def _fact_evidence(fact: Fact, chapter_number: int) -> FactEvidence:
    return FactEvidence(
        fact_id=fact.id,
        subject=fact.subject,
        predicate=fact.predicate,
        object=fact.object,
        fact_type=fact.fact_type,
        confidence=fact.confidence,
        source_quote=fact.source_quote,
        chapter_number=chapter_number,
        valid_from_chapter=fact.valid_from_chapter,
        valid_to_chapter=fact.valid_to_chapter,
    )


def _legacy_issues(
    mechanical: MechanicalEvaluationResult, critique: ChapterCritique | None
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = [
        {"source": "mechanical", "code": item.code, "severity": item.severity}
        for item in mechanical.issues
    ]
    if critique is not None:
        result.extend(
            {"source": "critic", "code": item.code, "severity": item.severity}
            for item in critique.issues
        )
    return result
