"""Full-book snapshot, analysis, critique, scoring, and persistence orchestration."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from sqlalchemy import select

from storyforge.agents import BookCriticAgent
from storyforge.book import (
    BookAnalysisBundle,
    BookEvaluationScorer,
    BookRevisionPlanner,
    ChapterTransitionAnalyzer,
    CharacterArcAnalyzer,
    ForeshadowingAnalyzer,
    PacingAnalyzer,
    PostgresVectorRepetitionDetector,
    RepetitionDetector,
    TimelineAnalyzer,
)
from storyforge.book.models import (
    AcceptedFactData,
    BookCriticContext,
    BookCritique,
    BookEvaluationResult,
    BookIssue,
    BookRevisionPlanData,
    ChapterRevisionPriority,
    ChapterRevisionTaskData,
    CharacterProfileData,
    ForeshadowingItemData,
    RelationshipPointData,
    RepetitionCandidate,
    SnapshotChapter,
)
from storyforge.database import SessionFactory
from storyforge.enums import (
    BookRevisionStatus,
    BookSnapshotStatus,
    FactStatus,
    GraphPredicate,
    KnowledgeStatus,
    MemoryStatus,
)
from storyforge.exceptions import EntityNotFoundError, InvalidStateError
from storyforge.models import (
    BookEvaluation,
    BookRevisionPlan,
    BookRevisionTask,
    BookRun,
    BookSnapshot,
    Chapter,
    ChapterTransitionEvaluation,
    Character,
    CharacterArcPoint,
    CharacterKnowledge,
    Evaluation,
    Fact,
    Foreshadowing,
    GraphRelation,
    Project,
    RelationshipHistory,
    TimelineEvent,
)
from storyforge.models.base import utc_now
from storyforge.repositories import (
    BookEvaluationRepository,
    BookRevisionPlanRepository,
    BookRunRepository,
    BookSnapshotRepository,
    ChapterTransitionRepository,
    CharacterArcRepository,
    CharacterKnowledgeRepository,
    RelationshipHistoryRepository,
    TimelineEventRepository,
)


class PeriodicBookChecker:
    """Run accepted-data-only global rules before the full snapshot exists."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._timeline = TimelineAnalyzer()
        self._characters = CharacterArcAnalyzer()
        self._foreshadowing = ForeshadowingAnalyzer()
        self._transitions = ChapterTransitionAnalyzer()
        self._pacing = PacingAnalyzer()
        self._repetition = RepetitionDetector()

    def check(self, run_id: int) -> dict[str, object]:
        chapters, facts, characters, foreshadowings, total_chapters = self._load(run_id)
        timeline = self._timeline.analyze(facts)
        arcs, knowledge, relationships = self._characters.analyze(chapters, facts, characters)
        foreshadowing = self._foreshadowing.analyze(foreshadowings, final_chapter=total_chapters)
        transitions = self._transitions.analyze(chapters)
        pacing = self._pacing.analyze(chapters)
        repetition = self._repetition.analyze(chapters)
        return {
            "through_chapter": max((item.chapter_number for item in chapters), default=0),
            "timeline_score": timeline.score,
            "critical_conflicts": sum(item.severity == "critical" for item in timeline.conflicts),
            "high_conflicts": sum(item.severity == "high" for item in timeline.conflicts),
            "character_arc_score": arcs.score,
            "knowledge_points": len(knowledge),
            "relationship_changes": len(relationships),
            "foreshadowing_payoff_rate": foreshadowing.payoff_rate,
            "pacing_score": pacing.score,
            "transition_issues": sum(len(item.issues) for item in transitions),
            "repetition_candidates": len(repetition.candidates),
        }

    def _load(
        self, run_id: int
    ) -> tuple[
        list[SnapshotChapter],
        list[AcceptedFactData],
        list[CharacterProfileData],
        list[ForeshadowingItemData],
        int,
    ]:
        with self._session_factory() as session:
            run = session.get(BookRun, run_id)
            if run is None:
                raise EntityNotFoundError(f"Book run {run_id} was not found")
            rows = list(
                session.scalars(
                    select(Chapter)
                    .where(
                        Chapter.project_id == run.project_id,
                        Chapter.accepted_version_id.is_not(None),
                    )
                    .order_by(Chapter.chapter_number)
                )
            )
            chapter_data: list[SnapshotChapter] = []
            for chapter in rows:
                version = chapter.accepted_version
                if version is None:
                    continue
                evaluation = next(
                    (
                        item
                        for item in reversed(chapter.evaluations)
                        if item.chapter_version_id == version.id
                    ),
                    None,
                )
                metadata = version.generation_metadata
                chapter_data.append(
                    SnapshotChapter(
                        chapter_id=chapter.id,
                        chapter_number=chapter.chapter_number,
                        chapter_version_id=version.id,
                        version=version.version,
                        title=version.title,
                        summary=version.summary,
                        word_count=version.word_count,
                        content=version.content,
                        evaluation_score=(
                            min(10.0, float(evaluation.overall_score))
                            if evaluation is not None
                            else 0
                        ),
                        outline_adherence=(
                            evaluation.outline_adherence_score if evaluation is not None else 0
                        ),
                        dialogue_ratio=(
                            float(evaluation.mechanical_metrics.get("dialogue_ratio", 0))
                            if evaluation is not None
                            else 0
                        ),
                        key_events=list(metadata.get("key_events", [])),
                        characters_present=list(metadata.get("characters_present", [])),
                        locations_present=list(metadata.get("locations_present", [])),
                    )
                )
            version_ids = [item.chapter_version_id for item in chapter_data]
            number_by_id = {item.chapter_id: item.chapter_number for item in chapter_data}
            fact_rows = list(
                session.scalars(
                    select(Fact)
                    .where(
                        Fact.project_id == run.project_id,
                        Fact.chapter_version_id.in_(version_ids),
                        Fact.status == FactStatus.ACCEPTED,
                    )
                    .order_by(Fact.chapter_id, Fact.id)
                )
            )
            fact_data = [
                AcceptedFactData(
                    id=fact.id,
                    chapter_id=fact.chapter_id,
                    chapter_version_id=fact.chapter_version_id,
                    chapter_number=number_by_id[fact.chapter_id],
                    subject=fact.subject,
                    predicate=fact.predicate,
                    object=fact.object,
                    confidence=fact.confidence,
                    evidence=fact.source_quote,
                    valid_from_chapter=fact.valid_from_chapter,
                    valid_to_chapter=fact.valid_to_chapter,
                )
                for fact in fact_rows
            ]
            character_data = [
                CharacterProfileData(
                    id=item.id,
                    name=item.name,
                    role=item.role,
                    goals=item.goals,
                    personality=item.personality,
                    current_state=item.current_state,
                    initial_knowledge=item.knowledge,
                )
                for item in session.scalars(
                    select(Character).where(Character.project_id == run.project_id)
                )
            ]
            foreshadowing_data = [
                ForeshadowingItemData(
                    id=item.id,
                    description=item.description,
                    importance=item.importance,
                    setup_chapter=item.setup_chapter,
                    expected_payoff_chapter=item.expected_payoff_chapter,
                    payoff_chapter=item.payoff_chapter,
                    status=item.status.value,
                )
                for item in session.scalars(
                    select(Foreshadowing).where(Foreshadowing.project_id == run.project_id)
                )
            ]
            return (
                chapter_data,
                fact_data,
                character_data,
                foreshadowing_data,
                run.total_chapters,
            )


class BookAnalysisService:
    """Analyze and persist one immutable accepted-version map transactionally."""

    def __init__(
        self,
        session_factory: SessionFactory,
        critic: BookCriticAgent,
        scorer: BookEvaluationScorer,
        revision_planner: BookRevisionPlanner,
    ) -> None:
        self._session_factory = session_factory
        self._critic = critic
        self._scorer = scorer
        self._revision_planner = revision_planner
        self._timeline = TimelineAnalyzer()
        self._characters = CharacterArcAnalyzer()
        self._foreshadowing = ForeshadowingAnalyzer()
        self._transitions = ChapterTransitionAnalyzer()
        self._pacing = PacingAnalyzer()
        self._repetition = RepetitionDetector()
        self._vector_repetition = PostgresVectorRepetitionDetector()

    def build_snapshot(self, run_id: int, *, allow_best: bool = False) -> BookSnapshot:
        """Freeze logical chapters to concrete immutable versions without copying prose."""
        with self._session_factory.begin() as session:
            run = BookRunRepository(session).get_for_update(run_id)
            if run is None:
                raise EntityNotFoundError(f"Book run {run_id} was not found")
            chapters = list(
                session.scalars(
                    select(Chapter)
                    .where(Chapter.project_id == run.project_id)
                    .order_by(Chapter.chapter_number)
                )
            )
            if len(chapters) != run.total_chapters:
                raise InvalidStateError("Book snapshot requires every planned chapter")
            mapping: dict[str, int] = {}
            total_words = 0
            accepted_count = 0
            for chapter in chapters:
                version = chapter.accepted_version
                if version is None and allow_best:
                    version = chapter.current_version
                if version is None:
                    raise InvalidStateError(
                        f"Chapter {chapter.chapter_number} has no accepted or best version"
                    )
                mapping[str(chapter.chapter_number)] = version.id
                total_words += version.word_count
                accepted_count += int(chapter.accepted_version_id == version.id)
            content_hash = hashlib.sha256(
                json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            repository = BookSnapshotRepository(session)
            existing = repository.by_hash(run.id, content_hash)
            if existing is not None:
                session.expunge(existing)
                return existing
            snapshot = repository.add(
                BookSnapshot(
                    project_id=run.project_id,
                    book_run_id=run.id,
                    snapshot_number=repository.next_number(run.id),
                    status=BookSnapshotStatus.CANDIDATE,
                    chapter_version_map=mapping,
                    total_words=total_words,
                    chapter_count=len(mapping),
                    accepted_chapter_count=accepted_count,
                    content_hash=content_hash,
                    evaluation_summary={},
                )
            )
            run.book_snapshot_id = snapshot.id
            if run.best_snapshot_id is None:
                run.best_snapshot_id = snapshot.id
            session.expunge(snapshot)
            return snapshot

    def analyze(self, snapshot_id: int) -> tuple[BookAnalysisBundle, BookEvaluationResult, int]:
        """Run global rules and governed critic, then persist one versioned evaluation."""
        snapshot, project, chapters, facts, characters, foreshadowings = self._load(snapshot_id)
        timeline = self._timeline.analyze(facts)
        arcs, knowledge, relationships = self._characters.analyze(chapters, facts, characters)
        graph_relationships = self._graph_relationships(project.id, chapters, characters)
        relationship_keys = {
            (
                item.subject_character_id,
                item.object_character_id,
                item.relationship_type,
                item.chapter_number,
            )
            for item in relationships
        }
        relationships.extend(
            item
            for item in graph_relationships
            if (
                item.subject_character_id,
                item.object_character_id,
                item.relationship_type,
                item.chapter_number,
            )
            not in relationship_keys
        )
        foreshadowing = self._foreshadowing.analyze(foreshadowings, final_chapter=len(chapters))
        transitions = self._transitions.analyze(chapters)
        pacing = self._pacing.analyze(chapters)
        repetition = self._repetition.analyze(chapters)
        vector_candidates = self._vector_repetition_candidates(project.id, chapters)
        if vector_candidates:
            repetition = repetition.model_copy(
                update={
                    "score": max(
                        0.0,
                        round(
                            repetition.score
                            - 0.5 * sum(not item.legitimate_callback for item in vector_candidates),
                            2,
                        ),
                    ),
                    "candidates": [*repetition.candidates, *vector_candidates],
                }
            )
        analysis = BookAnalysisBundle(
            timeline=timeline,
            character_arcs=arcs,
            knowledge=knowledge,
            relationships=relationships,
            foreshadowing=foreshadowing,
            transitions=transitions,
            pacing=pacing,
            repetition=repetition,
        )
        critic_result = self._critic.critique(self._critic_context(project, chapters, analysis))
        critique = self._merge_rule_issues(critic_result.output, analysis)
        scores = [item.evaluation_score for item in chapters]
        combined = self._scorer.score(
            chapter_scores=scores,
            ending_score=scores[-1] if scores else 0,
            analysis=analysis,
            critique=critique,
        )
        evaluation_id = self._persist_analysis(
            snapshot,
            analysis,
            critique,
            combined,
            provider=critic_result.provider,
            model=critic_result.model,
            prompt_versions=critic_result.prompt_versions,
        )
        return analysis, combined, evaluation_id

    def _graph_relationships(
        self,
        project_id: int,
        chapters: list[SnapshotChapter],
        characters: list[CharacterProfileData],
    ) -> list[RelationshipPointData]:
        """Project accepted snapshot graph edges into versioned character history."""
        version_to_chapter = {item.chapter_version_id: item.chapter_number for item in chapters}
        character_by_name = {"".join(item.name.casefold().split()): item for item in characters}
        allowed = {
            "trust",
            "friendship",
            "hostility",
            "family",
            "romance",
            "alliance",
            "mentorship",
            "authority",
        }
        result: list[RelationshipPointData] = []
        with self._session_factory() as session:
            relations = list(
                session.scalars(
                    select(GraphRelation)
                    .where(
                        GraphRelation.project_id == project_id,
                        GraphRelation.source_version_id.in_(list(version_to_chapter)),
                        GraphRelation.status == MemoryStatus.ACCEPTED,
                    )
                    .order_by(GraphRelation.valid_from_chapter, GraphRelation.id)
                )
            )
            for relation in relations:
                subject = character_by_name.get(
                    "".join(relation.subject_entity.canonical_name.casefold().split())
                )
                object_ = character_by_name.get(
                    "".join(relation.object_entity.canonical_name.casefold().split())
                )
                if subject is None or object_ is None or relation.source_version_id is None:
                    continue
                configured = str(relation.details.get("relationship_type", "")).casefold()
                if configured in allowed:
                    relationship_type = configured
                elif relation.predicate is GraphPredicate.CONFLICTS_WITH:
                    relationship_type = "hostility"
                elif relation.predicate is GraphPredicate.RELATED_TO:
                    relationship_type = "alliance"
                else:
                    continue
                result.append(
                    RelationshipPointData(
                        subject_character_id=subject.id,
                        object_character_id=object_.id,
                        relationship_type=relationship_type,  # type: ignore[arg-type]
                        value=str(relation.details.get("value", "active"))[:100],
                        chapter_number=version_to_chapter[relation.source_version_id],
                        chapter_version_id=relation.source_version_id,
                        evidence=relation.evidence[:160],
                    )
                )
        return result

    def _vector_repetition_candidates(
        self, project_id: int, chapters: list[SnapshotChapter]
    ) -> list[RepetitionCandidate]:
        """Execute semantic candidate discovery only on PostgreSQL/pgvector."""
        with self._session_factory() as session:
            return list(
                self._vector_repetition.analyze(session, project_id=project_id, chapters=chapters)
            )

    def build_revision_plan(
        self,
        *,
        snapshot_id: int,
        revision_round: int,
        evaluation: BookEvaluationResult,
        critique: BookCritique,
        maximum_chapters: int,
        remaining_calls: int,
        remaining_tokens: int,
        remaining_cost: Decimal,
    ) -> BookRevisionPlanData:
        with self._session_factory() as session:
            snapshot = BookSnapshotRepository(session).get(snapshot_id)
            if snapshot is None:
                raise EntityNotFoundError(f"Book snapshot {snapshot_id} was not found")
            facts = list(
                session.scalars(
                    select(Fact).where(
                        Fact.project_id == snapshot.project_id,
                        Fact.status == FactStatus.ACCEPTED,
                    )
                )
            )
            preserved = [f"{fact.subject} {fact.predicate} {fact.object}" for fact in facts[:50]]
            run_id = snapshot.book_run_id
            total_chapters = snapshot.chapter_count
        planner = BookRevisionPlanner(maximum_chapters=maximum_chapters)
        data = planner.build(
            snapshot_id=snapshot_id,
            revision_round=revision_round,
            total_chapters=total_chapters,
            evaluation=evaluation,
            critique=critique,
            remaining_calls=remaining_calls,
            remaining_tokens=remaining_tokens,
            remaining_cost=remaining_cost,
            preserve_facts=preserved,
        )
        with self._session_factory.begin() as session:
            repository = BookRevisionPlanRepository(session)
            existing = repository.latest_for_snapshot(snapshot_id)
            if existing is not None and existing.revision_round == revision_round:
                return self._plan_data(existing)
            plan = repository.add(
                BookRevisionPlan(
                    project_id=snapshot.project_id,
                    book_run_id=run_id,
                    book_snapshot_id=snapshot_id,
                    revision_round=revision_round,
                    global_objectives=data.global_objectives,
                    dependency_order=data.dependency_order,
                    must_preserve=data.must_preserve,
                    global_constraints=data.global_constraints,
                    estimated_calls=data.estimated_calls,
                    estimated_tokens=data.estimated_tokens,
                    estimated_cost=data.estimated_cost,
                    status=BookRevisionStatus.PENDING,
                )
            )
            for order, item in enumerate(data.chapter_tasks, start=1):
                session.add(
                    BookRevisionTask(
                        plan_id=plan.id,
                        chapter_number=item.chapter_number,
                        priority=item.priority,
                        issue_codes=item.issue_codes,
                        objective=item.objective,
                        required_changes=item.required_changes,
                        preserve_facts=item.preserve_facts,
                        affected_future_chapters=item.affected_future_chapters,
                        rerun_global_checks=item.rerun_global_checks,
                        dependency_order=order,
                    )
                )
        return data

    def accept_snapshot(self, snapshot_id: int, *, needs_review: bool = False) -> None:
        with self._session_factory.begin() as session:
            snapshot = BookSnapshotRepository(session).get(snapshot_id)
            if snapshot is None:
                raise EntityNotFoundError(f"Book snapshot {snapshot_id} was not found")
            if not needs_review:
                old = BookSnapshotRepository(session).accepted_for_project(snapshot.project_id)
                if old is not None and old.id != snapshot.id:
                    old.status = BookSnapshotStatus.SUPERSEDED
                snapshot.status = BookSnapshotStatus.ACCEPTED
                snapshot.accepted_at = utc_now()
            else:
                snapshot.status = BookSnapshotStatus.NEEDS_REVIEW

    def _load(
        self, snapshot_id: int
    ) -> tuple[
        BookSnapshot,
        Project,
        list[SnapshotChapter],
        list[AcceptedFactData],
        list[CharacterProfileData],
        list[ForeshadowingItemData],
    ]:
        with self._session_factory() as session:
            snapshot = BookSnapshotRepository(session).get(snapshot_id)
            if snapshot is None:
                raise EntityNotFoundError(f"Book snapshot {snapshot_id} was not found")
            project = session.get(Project, snapshot.project_id)
            if project is None:
                raise EntityNotFoundError("Book snapshot project was not found")
            version_ids = list(snapshot.chapter_version_map.values())
            rows = list(
                session.execute(
                    select(Chapter, Evaluation)
                    .join(
                        Evaluation,
                        (Evaluation.chapter_id == Chapter.id)
                        & (Evaluation.chapter_version_id == Chapter.accepted_version_id),
                        isouter=True,
                    )
                    .where(Chapter.project_id == snapshot.project_id)
                    .order_by(Chapter.chapter_number, Evaluation.evaluation_version.desc())
                )
            )
            chapter_data: list[SnapshotChapter] = []
            seen: set[int] = set()
            for chapter, evaluation in rows:
                version_id = snapshot.chapter_version_map.get(str(chapter.chapter_number))
                if version_id is None or chapter.id in seen:
                    continue
                version = next((item for item in chapter.versions if item.id == version_id), None)
                if version is None:
                    raise InvalidStateError("Snapshot references a missing chapter version")
                seen.add(chapter.id)
                metadata = version.generation_metadata
                score = float(evaluation.overall_score) if evaluation is not None else 0.0
                chapter_data.append(
                    SnapshotChapter(
                        chapter_id=chapter.id,
                        chapter_number=chapter.chapter_number,
                        chapter_version_id=version.id,
                        version=version.version,
                        title=version.title,
                        summary=version.summary,
                        word_count=version.word_count,
                        content=version.content,
                        evaluation_score=min(10.0, score),
                        outline_adherence=(
                            evaluation.outline_adherence_score if evaluation is not None else 0
                        ),
                        dialogue_ratio=(
                            float(evaluation.mechanical_metrics.get("dialogue_ratio", 0))
                            if evaluation is not None
                            else 0
                        ),
                        key_events=list(metadata.get("key_events", [])),
                        characters_present=list(metadata.get("characters_present", [])),
                        locations_present=list(metadata.get("locations_present", [])),
                    )
                )
            fact_rows = list(
                session.scalars(
                    select(Fact, Chapter.chapter_number)
                    .join(Chapter, Chapter.id == Fact.chapter_id)
                    .where(
                        Fact.project_id == snapshot.project_id,
                        Fact.chapter_version_id.in_(version_ids),
                        Fact.status == FactStatus.ACCEPTED,
                    )
                    .order_by(Chapter.chapter_number, Fact.id)
                )
            )
            # SQLAlchemy scalar projection above returns Fact; derive chapter number by identity.
            number_by_id = {item.chapter_id: item.chapter_number for item in chapter_data}
            fact_data = [
                AcceptedFactData(
                    id=fact.id,
                    chapter_id=fact.chapter_id,
                    chapter_version_id=fact.chapter_version_id,
                    chapter_number=number_by_id[fact.chapter_id],
                    subject=fact.subject,
                    predicate=fact.predicate,
                    object=fact.object,
                    confidence=fact.confidence,
                    evidence=fact.source_quote,
                    valid_from_chapter=fact.valid_from_chapter,
                    valid_to_chapter=fact.valid_to_chapter,
                )
                for fact in fact_rows
            ]
            character_data = [
                CharacterProfileData(
                    id=item.id,
                    name=item.name,
                    role=item.role,
                    goals=item.goals,
                    personality=item.personality,
                    current_state=item.current_state,
                    initial_knowledge=item.knowledge,
                )
                for item in session.scalars(
                    select(Character)
                    .where(Character.project_id == snapshot.project_id)
                    .order_by(Character.id)
                )
            ]
            foreshadowing_data = [
                ForeshadowingItemData(
                    id=item.id,
                    description=item.description,
                    importance=item.importance,
                    setup_chapter=item.setup_chapter,
                    expected_payoff_chapter=item.expected_payoff_chapter,
                    payoff_chapter=item.payoff_chapter,
                    status=item.status.value,
                )
                for item in session.scalars(
                    select(Foreshadowing)
                    .where(Foreshadowing.project_id == snapshot.project_id)
                    .order_by(Foreshadowing.id)
                )
            ]
            session.expunge(snapshot)
            session.expunge(project)
        return snapshot, project, chapter_data, fact_data, character_data, foreshadowing_data

    @staticmethod
    def _critic_context(
        project: Project, chapters: list[SnapshotChapter], analysis: BookAnalysisBundle
    ) -> BookCriticContext:
        return BookCriticContext(
            project_title=project.title,
            premise=project.premise,
            book_summary=" ".join(item.summary for item in chapters),
            chapter_summaries=[
                {
                    "chapter_number": item.chapter_number,
                    "title": item.title,
                    "summary": item.summary,
                    "score": item.evaluation_score,
                }
                for item in chapters
            ],
            timeline_summary={
                "events": len(analysis.timeline.events),
                "conflicts": len(analysis.timeline.conflicts),
                "codes": [item.code for item in analysis.timeline.conflicts],
            },
            character_arc_summary={
                "score": analysis.character_arcs.score,
                "points": len(analysis.character_arcs.points),
                "issues": [item.code for item in analysis.character_arcs.issues],
            },
            relationship_summary=[
                {
                    "chapter_number": item.chapter_number,
                    "relationship_type": item.relationship_type,
                    "value": item.value,
                }
                for item in analysis.relationships[:100]
            ],
            foreshadowing_summary={
                "total": analysis.foreshadowing.total,
                "payoff_rate": analysis.foreshadowing.payoff_rate,
                "issues": [item.code for item in analysis.foreshadowing.issues],
            },
            pacing_summary={
                "score": analysis.pacing.score,
                "issues": [item.code for item in analysis.pacing.issues],
            },
            transition_summary={
                "count": len(analysis.transitions),
                "issues": [item.code for result in analysis.transitions for item in result.issues],
            },
            repetition_summary={
                "score": analysis.repetition.score,
                "candidates": len(analysis.repetition.candidates),
            },
            chapter_score_trend=[item.evaluation_score for item in chapters],
        )

    @staticmethod
    def _merge_rule_issues(critique: BookCritique, analysis: BookAnalysisBundle) -> BookCritique:
        issues = list(critique.global_issues)
        for timeline_issue in analysis.timeline.conflicts:
            issues.append(
                BookIssue(
                    code=timeline_issue.code,
                    category="timeline",
                    severity=timeline_issue.severity,
                    description=timeline_issue.description,
                    chapter_numbers=timeline_issue.chapter_numbers,
                    evidence=timeline_issue.evidence,
                    suggestion=timeline_issue.suggested_resolution,
                )
            )
        for arc_issue in analysis.character_arcs.issues:
            issues.append(
                BookIssue(
                    code=arc_issue.code,
                    category="character",
                    severity=arc_issue.severity,
                    description=arc_issue.description,
                    chapter_numbers=arc_issue.chapter_numbers,
                    evidence=arc_issue.evidence,
                    suggestion="Add an accepted event that explains the state change.",
                )
            )
        for foreshadowing_issue in analysis.foreshadowing.issues:
            issues.append(
                BookIssue(
                    code=foreshadowing_issue.code,
                    category="foreshadowing",
                    severity=foreshadowing_issue.severity,
                    description=foreshadowing_issue.description,
                    chapter_numbers=foreshadowing_issue.chapter_numbers,
                    evidence=foreshadowing_issue.evidence,
                    suggestion="Revise the setup/payoff order or explicitly leave it open.",
                )
            )
        for pacing_issue in analysis.pacing.issues:
            issues.append(
                BookIssue(
                    code=pacing_issue.code,
                    category="pacing",
                    severity=pacing_issue.severity,
                    description=pacing_issue.description,
                    chapter_numbers=pacing_issue.chapter_numbers,
                    suggestion="Rebalance the selected chapter without changing accepted canon.",
                )
            )
        for transition_result in analysis.transitions:
            for transition_issue in transition_result.issues:
                issues.append(
                    BookIssue(
                        code=transition_issue.code,
                        category="transition",
                        severity=transition_issue.severity,
                        description=transition_issue.description,
                        chapter_numbers=[
                            transition_result.from_chapter,
                            transition_result.to_chapter,
                        ],
                        evidence=[transition_issue.evidence] if transition_issue.evidence else [],
                        suggestion="Add a brief, evidence-consistent transition.",
                    )
                )
        for repetition_issue in analysis.repetition.candidates:
            if repetition_issue.legitimate_callback:
                continue
            issues.append(
                BookIssue(
                    code=repetition_issue.code,
                    category="repetition",
                    severity=repetition_issue.severity,
                    description="A high-similarity passage or scene requires review.",
                    chapter_numbers=repetition_issue.chapter_numbers,
                    evidence=repetition_issue.evidence,
                    suggestion="Differentiate the scene or document the intentional callback.",
                )
            )
        unique = {f"{item.code}:{item.chapter_numbers}": item for item in issues}
        merged = list(unique.values())
        priorities = [
            ChapterRevisionPriority(
                chapter_number=chapter,
                priority=index,
                issue_codes=sorted(
                    {item.code for item in merged if chapter in item.chapter_numbers}
                ),
                objective="Resolve the chapter's highest-severity global issues.",
            )
            for index, chapter in enumerate(
                sorted({number for item in merged for number in item.chapter_numbers}), start=1
            )
        ]
        return BookCritique.model_validate(
            {
                **critique.model_dump(mode="python"),
                "global_issues": [item.model_dump(mode="python") for item in merged],
                "chapter_priorities": [item.model_dump(mode="python") for item in priorities],
                "pass_recommendation": critique.pass_recommendation
                and not any(item.severity == "critical" for item in merged),
            }
        )

    def _persist_analysis(
        self,
        snapshot: BookSnapshot,
        analysis: BookAnalysisBundle,
        critique: BookCritique,
        combined: BookEvaluationResult,
        *,
        provider: str,
        model: str,
        prompt_versions: dict[str, str],
    ) -> int:
        key = f"book-evaluation:{snapshot.id}:{snapshot.content_hash}:v1"
        with self._session_factory.begin() as session:
            evaluation_repository = BookEvaluationRepository(session)
            existing = evaluation_repository.by_idempotency_key(key)
            if existing is not None:
                return existing.id
            timeline_repository = TimelineEventRepository(session)
            for timeline_event in analysis.timeline.events:
                timeline_repository.add(
                    TimelineEvent(
                        project_id=snapshot.project_id,
                        book_snapshot_id=snapshot.id,
                        chapter_id=timeline_event.chapter_id,
                        chapter_version_id=timeline_event.chapter_version_id,
                        event_key=timeline_event.event_key,
                        title=timeline_event.title,
                        description=timeline_event.description,
                        story_time=timeline_event.story_time,
                        sequence_index=timeline_event.sequence_index,
                        location_id=None,
                        participant_entity_ids=[],
                        causes_event_ids=[],
                        consequence_event_ids=[],
                        confidence=timeline_event.confidence,
                        status="accepted",
                        evidence=timeline_event.evidence,
                    )
                )
            arc_repository = CharacterArcRepository(session)
            for arc_point in analysis.character_arcs.points:
                arc_repository.add(
                    CharacterArcPoint(
                        project_id=snapshot.project_id,
                        book_snapshot_id=snapshot.id,
                        character_id=arc_point.character_id,
                        chapter_number=arc_point.chapter_number,
                        chapter_version_id=arc_point.chapter_version_id,
                        goals=arc_point.goals,
                        emotional_state=arc_point.emotional_state,
                        physical_state=arc_point.physical_state,
                        location=arc_point.location,
                        relationships=arc_point.relationships,
                        knowledge=arc_point.knowledge,
                        conflicts=arc_point.conflicts,
                        decisions=arc_point.decisions,
                        evidence=arc_point.evidence,
                    )
                )
            knowledge_repository = CharacterKnowledgeRepository(session)
            for knowledge_item in analysis.knowledge:
                knowledge_repository.add(
                    CharacterKnowledge(
                        project_id=snapshot.project_id,
                        book_snapshot_id=snapshot.id,
                        character_id=knowledge_item.character_id,
                        fact_id=knowledge_item.fact_id,
                        learned_chapter=knowledge_item.learned_chapter,
                        source_event_id=None,
                        confidence=knowledge_item.confidence,
                        status=KnowledgeStatus(knowledge_item.status),
                    )
                )
            relationship_repository = RelationshipHistoryRepository(session)
            for relationship_item in analysis.relationships:
                relationship_repository.add(
                    RelationshipHistory(
                        project_id=snapshot.project_id,
                        book_snapshot_id=snapshot.id,
                        subject_character_id=relationship_item.subject_character_id,
                        object_character_id=relationship_item.object_character_id,
                        relationship_type=relationship_item.relationship_type,
                        value=relationship_item.value,
                        chapter_number=relationship_item.chapter_number,
                        chapter_version_id=relationship_item.chapter_version_id,
                        event_id=None,
                        valid_from_chapter=relationship_item.chapter_number,
                        valid_to_chapter=None,
                        status="accepted",
                        evidence=relationship_item.evidence,
                    )
                )
            transition_repository = ChapterTransitionRepository(session)
            for transition_result in analysis.transitions:
                transition_repository.add(
                    ChapterTransitionEvaluation(
                        book_snapshot_id=snapshot.id,
                        from_chapter=transition_result.from_chapter,
                        to_chapter=transition_result.to_chapter,
                        score=transition_result.score,
                        issues=[
                            value.model_dump(mode="json") for value in transition_result.issues
                        ],
                        strengths=transition_result.strengths,
                    )
                )
            evaluation = evaluation_repository.add(
                BookEvaluation(
                    project_id=snapshot.project_id,
                    book_run_id=snapshot.book_run_id,
                    book_snapshot_id=snapshot.id,
                    evaluation_version=1,
                    final_score=combined.final_score,
                    passed=combined.passed,
                    dimension_scores=combined.dimension_scores,
                    blocking_reasons=combined.blocking_reasons,
                    recommended_action=combined.recommended_action,
                    priority_chapters=combined.priority_chapters,
                    global_issues=[item.model_dump(mode="json") for item in critique.global_issues],
                    critique=critique.model_dump(mode="json"),
                    evaluator_versions={
                        "timeline": analysis.timeline.checker_version,
                        "global_rules": "book-analysis-v1",
                        "provider": provider,
                        "model": model,
                    },
                    prompt_versions=prompt_versions,
                    idempotency_key=key,
                )
            )
            snapshot_row = BookSnapshotRepository(session).get(snapshot.id)
            if snapshot_row is not None:
                snapshot_row.status = BookSnapshotStatus.REVIEWED
                snapshot_row.evaluation_summary = {
                    "evaluation_id": evaluation.id,
                    "final_score": combined.final_score,
                    "passed": combined.passed,
                    "recommended_action": combined.recommended_action,
                    "timeline_events": len(analysis.timeline.events),
                    "timeline_conflicts": len(analysis.timeline.conflicts),
                    "character_arc_points": len(analysis.character_arcs.points),
                    "knowledge_points": len(analysis.knowledge),
                    "relationship_changes": len(analysis.relationships),
                    "foreshadowing_payoff_rate": analysis.foreshadowing.payoff_rate,
                    "transition_average": (
                        round(
                            sum(item.score for item in analysis.transitions)
                            / len(analysis.transitions),
                            2,
                        )
                        if analysis.transitions
                        else 10.0
                    ),
                    "pacing_score": analysis.pacing.score,
                    "repetition_score": analysis.repetition.score,
                }
            return evaluation.id

    @staticmethod
    def _plan_data(plan: BookRevisionPlan) -> BookRevisionPlanData:
        return BookRevisionPlanData(
            book_snapshot_id=plan.book_snapshot_id,
            revision_round=plan.revision_round,
            global_objectives=plan.global_objectives,
            chapter_tasks=[
                ChapterRevisionTaskData(
                    chapter_number=item.chapter_number,
                    priority=item.priority,
                    issue_codes=item.issue_codes,
                    objective=item.objective,
                    required_changes=item.required_changes,
                    preserve_facts=item.preserve_facts,
                    affected_future_chapters=item.affected_future_chapters,
                    rerun_global_checks=item.rerun_global_checks,
                )
                for item in plan.tasks
            ],
            dependency_order=plan.dependency_order,
            must_preserve=plan.must_preserve,
            global_constraints=plan.global_constraints,
            estimated_calls=plan.estimated_calls,
            estimated_tokens=plan.estimated_tokens,
            estimated_cost=plan.estimated_cost,
        )
