"""Version-scoped drafting, candidate extraction, revision, and acceptance services."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import select

from storyforge.agents import FactExtractorAgent, RevisionAgent, WriterAgent
from storyforge.consistency.normalizer import FactNormalizer
from storyforge.database import SessionFactory
from storyforge.enums import (
    ChapterStatus,
    ChapterVersionStatus,
    ConflictSeverity,
    ConflictStatus,
    FactStatus,
    ForeshadowingStatus,
    WorkflowRunStatus,
)
from storyforge.exceptions import EntityNotFoundError, InvalidStateError
from storyforge.memory import MemoryIndexService
from storyforge.models import (
    ChapterVersion,
    Conflict,
    Evaluation,
    Fact,
    Foreshadowing,
    Revision,
    VersionComparison,
)
from storyforge.repositories import (
    ChapterRepository,
    ChapterVersionRepository,
    CharacterRepository,
    EvaluationRepository,
    FactRepository,
    ForeshadowingRepository,
    ProjectRepository,
    VersionComparisonRepository,
    WorkflowRunRepository,
)
from storyforge.revision import (
    AcceptanceEvaluator,
    ComparisonDimension,
    EvaluationSnapshot,
    RevisionAgentRequest,
    RevisionBrief,
    RevisionBriefBuilder,
    RevisionIssue,
    VersionComparisonResult,
)
from storyforge.schemas.context import ChapterContext, ContextBuildRequest
from storyforge.schemas.generation import FactExtractionRequest
from storyforge.services.context_builder import ContextBuilder

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VersionArtifact:
    """Small graph-safe projection of one persisted chapter version."""

    version_id: int
    version_number: int
    created: bool


@dataclass(frozen=True, slots=True)
class ExtractionArtifact:
    """Small graph-safe result of candidate fact extraction."""

    version_id: int
    fact_count: int
    created: bool


class ChapterVersionService:
    """Own all side effects around immutable chapter text versions."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context_builder: ContextBuilder,
        writer: WriterAgent,
        fact_extractor: FactExtractorAgent,
        revision_agent: RevisionAgent,
        brief_builder: RevisionBriefBuilder,
        acceptance: AcceptanceEvaluator,
        memory_index: MemoryIndexService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._context_builder = context_builder
        self._writer = writer
        self._extractor = fact_extractor
        self._revision_agent = revision_agent
        self._brief_builder = brief_builder
        self._acceptance = acceptance
        self._memory_index = memory_index

    def load_context(self, project_id: int, chapter_number: int) -> ChapterContext:
        """Delegate future-safe context construction to the existing ContextBuilder."""
        return self._context_builder.build(
            ContextBuildRequest(project_id=project_id, chapter_number=chapter_number)
        )

    def ensure_initial_version(
        self,
        *,
        project_id: int,
        chapter_number: int,
        workflow_run_id: int,
        context: ChapterContext,
    ) -> VersionArtifact:
        """Reuse an existing current version or create one idempotent candidate draft."""
        key = f"workflow:{workflow_run_id}:generate_draft:0"
        with self._session_factory() as session:
            chapter = ChapterRepository(session).get_by_number(project_id, chapter_number)
            if chapter is None:
                raise EntityNotFoundError("Workflow chapter was not found")
            existing = ChapterVersionRepository(session).get_by_idempotency_key(key)
            if existing is not None:
                return VersionArtifact(existing.id, existing.version, False)
            if chapter.current_version_id is not None:
                current = ChapterVersionRepository(session).get(chapter.current_version_id)
                if current is not None:
                    return VersionArtifact(current.id, current.version, False)

        result = self._writer.write(context)
        with self._session_factory.begin() as session:
            chapter = ChapterRepository(session).get_by_number(project_id, chapter_number)
            if chapter is None:
                raise EntityNotFoundError("Workflow chapter disappeared while drafting")
            repository = ChapterVersionRepository(session)
            replay = repository.get_by_idempotency_key(key)
            if replay is not None:
                return VersionArtifact(replay.id, replay.version, False)
            version_number = repository.next_version(chapter.id)
            version = repository.add(
                ChapterVersion(
                    chapter_id=chapter.id,
                    version=version_number,
                    title=result.output.title,
                    content=result.output.content,
                    summary=result.output.summary,
                    status=ChapterVersionStatus.DRAFT,
                    source="generated",
                    workflow_run_id=workflow_run_id,
                    word_count=_word_count(result.output.content),
                    provider=result.provider,
                    model=result.model,
                    prompt_versions=result.prompt_versions,
                    generation_metadata={
                        "attempts": result.attempts,
                        "duration_ms": result.duration_ms,
                        "style_self_check": result.output.style_self_check.model_dump(mode="json"),
                        "new_entities": [
                            item.model_dump(mode="json") for item in result.output.new_entities
                        ],
                    },
                    idempotency_key=key,
                )
            )
            chapter.current_version_id = version.id
            chapter.version = version.version
            chapter.status = ChapterStatus.DRAFTING
            run = WorkflowRunRepository(session).get(workflow_run_id)
            if run is not None:
                run.current_version_id = version.id
                run.original_version_id = run.original_version_id or version.id
                run.best_version_id = run.best_version_id or version.id
                run.prompt_versions = {**run.prompt_versions, **result.prompt_versions}
            return VersionArtifact(version.id, version.version, True)

    def extract_candidate_facts(
        self,
        *,
        project_id: int,
        chapter_number: int,
        version_id: int,
        workflow_run_id: int,
    ) -> ExtractionArtifact:
        """Extract and persist version-scoped candidates without canonical side effects."""
        with self._session_factory() as session:
            version = ChapterVersionRepository(session).get(version_id)
            if version is None:
                raise EntityNotFoundError("Chapter version was not found for extraction")
            existing = FactRepository(session).list_for_version(version_id)
            if (
                existing
                or version.candidate_character_updates
                or version.candidate_foreshadowing_updates
                or "fact_extraction" in version.generation_metadata
            ):
                return ExtractionArtifact(version_id, len(existing), False)
            new_entities = version.generation_metadata.get("new_entities", [])
            request = FactExtractionRequest(
                project_id=project_id,
                chapter_number=chapter_number,
                chapter_content=version.content,
                context_summary=version.summary,
                new_entities=new_entities,
            )
        result = self._extractor.extract(request)
        normalizer = FactNormalizer()
        with self._session_factory.begin() as session:
            version = ChapterVersionRepository(session).get(version_id)
            if version is None:
                raise EntityNotFoundError("Chapter version disappeared during extraction")
            repository = FactRepository(session)
            existing = repository.list_for_version(version_id)
            if (
                existing
                or version.candidate_character_updates
                or version.candidate_foreshadowing_updates
                or "fact_extraction" in version.generation_metadata
            ):
                return ExtractionArtifact(version_id, len(existing), False)
            hashes: set[str] = set()
            for item in result.output.facts:
                normalized_hash = normalizer.identity_hash(
                    item.subject, item.predicate, item.object
                )
                if normalized_hash in hashes:
                    continue
                hashes.add(normalized_hash)
                repository.add(
                    Fact(
                        project_id=project_id,
                        chapter_id=version.chapter_id,
                        chapter_version_id=version.id,
                        workflow_run_id=workflow_run_id,
                        status=FactStatus.CANDIDATE,
                        normalized_hash=normalized_hash,
                        subject=item.subject,
                        predicate=item.predicate,
                        object=item.object,
                        fact_type=item.fact_type,
                        confidence=item.confidence,
                        source_quote=item.source_quote,
                        valid_from_chapter=item.valid_from_chapter,
                        valid_to_chapter=item.valid_to_chapter,
                    )
                )
            version.candidate_character_updates = [
                item.model_dump(mode="json") for item in result.output.character_updates
            ]
            version.candidate_foreshadowing_updates = [
                item.model_dump(mode="json") for item in result.output.foreshadowing_updates
            ]
            version.generation_metadata = {
                **version.generation_metadata,
                "fact_extraction": {
                    "provider": result.provider,
                    "model": result.model,
                    "prompt_versions": result.prompt_versions,
                    "attempts": result.attempts,
                    "duration_ms": result.duration_ms,
                },
            }
            run = WorkflowRunRepository(session).get(workflow_run_id)
            if run is not None:
                run.prompt_versions = {**run.prompt_versions, **result.prompt_versions}
            return ExtractionArtifact(version_id, len(hashes), True)

    def build_revision_brief(
        self,
        *,
        workflow_run_id: int,
        source_version_id: int,
        evaluation_id: int,
        revision_attempt: int,
        previous_improved: bool | None,
    ) -> RevisionBrief:
        """Build a bounded brief from persisted M4 issues and conflicts."""
        with self._session_factory() as session:
            version = ChapterVersionRepository(session).get(source_version_id)
            evaluation = EvaluationRepository(session).get(evaluation_id)
            run = WorkflowRunRepository(session).get(workflow_run_id)
            if version is None or evaluation is None or run is None:
                raise EntityNotFoundError("Revision brief inputs were not found")
            chapter = ChapterRepository(session).get(version.chapter_id)
            project = ProjectRepository(session).get(run.project_id)
            if chapter is None or project is None:
                raise EntityNotFoundError("Revision brief chapter or project was not found")
            issues = [
                RevisionIssue(
                    code=item.code,
                    category=item.category,
                    severity=item.severity,
                    problem=item.description,
                    evidence=item.evidence,
                    suggestion=item.suggestion or f"Resolve {item.code}.",
                    source="critic" if item.source == "critic" else "mechanical",
                )
                for item in evaluation.issue_records
            ]
            issues.extend(
                RevisionIssue(
                    code=item.rule_code,
                    category="consistency",
                    severity=item.severity,
                    problem=item.description,
                    evidence=item.new_evidence,
                    suggestion=item.suggested_resolution,
                    source="consistency",
                )
                for item in evaluation.conflicts
            )
            for code in evaluation.blocking_reasons:
                if code not in {item.code for item in issues}:
                    issues.append(
                        RevisionIssue(
                            code=code,
                            category="blocking",
                            severity=ConflictSeverity.HIGH,
                            problem=code.replace("_", " "),
                            suggestion=f"Remove the blocking condition {code}.",
                            source="blocking",
                        )
                    )
            accepted_facts = list(
                session.scalars(
                    select(Fact).where(
                        Fact.project_id == project.id,
                        Fact.status == FactStatus.ACCEPTED,
                        Fact.valid_from_chapter <= chapter.chapter_number,
                    )
                )
            )
            must_preserve = [
                f"{item.subject} | {item.predicate} | {item.object}" for item in accepted_facts
            ]
            forbidden = [
                str(item) for item in chapter.outline_metadata.get("forbidden_reveals", [])
            ]
            return self._brief_builder.build(
                chapter_id=chapter.id,
                source_version_id=version.id,
                revision_attempt=revision_attempt,
                objective=chapter.objective,
                issues=issues,
                must_preserve_facts=must_preserve,
                forbidden_changes=forbidden,
                target_words=project.target_words_per_chapter,
                previous_improved=previous_improved,
            )

    def revise(
        self,
        *,
        workflow_run_id: int,
        source_version_id: int,
        brief: RevisionBrief,
        context: ChapterContext,
    ) -> VersionArtifact:
        """Create a new immutable revision version with an idempotency key."""
        key = f"workflow:{workflow_run_id}:revise_draft:{brief.revision_attempt}"
        with self._session_factory() as session:
            repository = ChapterVersionRepository(session)
            existing = repository.get_by_idempotency_key(key)
            if existing is not None:
                return VersionArtifact(existing.id, existing.version, False)
            source = repository.get(source_version_id)
            run = WorkflowRunRepository(session).get(workflow_run_id)
            if source is None or run is None:
                raise EntityNotFoundError("Revision source or workflow was not found")
            chapter = ChapterRepository(session).get(source.chapter_id)
            project = ProjectRepository(session).get(run.project_id)
            if chapter is None or project is None:
                raise EntityNotFoundError("Revision chapter or project was not found")
            request = RevisionAgentRequest(
                chapter_id=chapter.id,
                source_version_id=source.id,
                original_title=source.title,
                original_content=source.content,
                original_summary=source.summary,
                outline=dict(chapter.outline_metadata),
                character_states={item.name: item.current_state for item in context.characters},
                story_rules=[item.statement for item in context.rules],
                accepted_facts=[
                    f"{item.subject} | {item.predicate} | {item.object}"
                    for item in context.known_facts
                ],
                active_foreshadowing=[item.description for item in context.active_foreshadowing],
                style_guide=context.project.style_guide,
                brief=brief,
            )
        result = self._revision_agent.revise(request)
        with self._session_factory.begin() as session:
            repository = ChapterVersionRepository(session)
            replay = repository.get_by_idempotency_key(key)
            if replay is not None:
                return VersionArtifact(replay.id, replay.version, False)
            source = repository.get(source_version_id)
            run = WorkflowRunRepository(session).get(workflow_run_id)
            if source is None or run is None:
                raise EntityNotFoundError("Revision source or workflow disappeared")
            chapter = ChapterRepository(session).get(source.chapter_id)
            if chapter is None:
                raise EntityNotFoundError("Revision chapter disappeared")
            version_number = repository.next_version(chapter.id)
            version = repository.add(
                ChapterVersion(
                    chapter_id=chapter.id,
                    version=version_number,
                    title=result.output.title,
                    content=result.output.content,
                    summary=result.output.summary,
                    status=ChapterVersionStatus.REVISION,
                    source="revision",
                    parent_version_id=source.id,
                    workflow_run_id=workflow_run_id,
                    word_count=_word_count(result.output.content),
                    provider=result.provider,
                    model=result.model,
                    prompt_versions=result.prompt_versions,
                    generation_metadata={
                        "changes_made": result.output.changes_made,
                        "unresolved_items": result.output.unresolved_items,
                        "key_events": result.output.key_events,
                        "characters_present": result.output.characters_present,
                        "locations_present": result.output.locations_present,
                    },
                    idempotency_key=key,
                )
            )
            source_evaluation = EvaluationRepository(session).latest_for_version(source.id)
            session.add(
                Revision(
                    chapter_id=chapter.id,
                    previous_version=source.version,
                    new_version=version.version,
                    source_version_id=source.id,
                    new_version_id=version.id,
                    workflow_run_id=workflow_run_id,
                    reason=brief.objective,
                    score_before=source_evaluation.overall_score if source_evaluation else 0,
                    score_after=0,
                    accepted=False,
                    status="created",
                    brief=brief.model_dump(mode="json"),
                    prompt_versions=result.prompt_versions,
                )
            )
            chapter.current_version_id = version.id
            chapter.version = version.version
            chapter.status = ChapterStatus.REVISING
            run.current_version_id = version.id
            run.revision_attempt = brief.revision_attempt
            run.retry_count = brief.revision_attempt
            run.prompt_versions = {**run.prompt_versions, **result.prompt_versions}
            return VersionArtifact(version.id, version.version, True)

    def compare_versions(
        self,
        *,
        workflow_run_id: int,
        old_version_id: int,
        new_version_id: int,
        revision_attempt: int,
        max_revision_attempts: int,
    ) -> VersionComparisonResult:
        """Compare and persist one idempotent version decision."""
        with self._session_factory.begin() as session:
            repository = VersionComparisonRepository(session)
            existing = repository.get_for_new_version(workflow_run_id, new_version_id)
            if existing is not None:
                return _comparison_result(existing)
            old_eval = EvaluationRepository(session).latest_for_version(old_version_id)
            new_eval = EvaluationRepository(session).latest_for_version(new_version_id)
            revision = session.scalar(
                select(Revision).where(
                    Revision.workflow_run_id == workflow_run_id,
                    Revision.new_version_id == new_version_id,
                )
            )
            if old_eval is None or new_eval is None or revision is None:
                raise InvalidStateError("Both versions and the revision brief must be evaluated")
            brief = RevisionBrief.model_validate(revision.brief)
            result = self._acceptance.compare(
                _evaluation_snapshot(old_eval),
                _evaluation_snapshot(new_eval),
                brief,
                revision_attempt=revision_attempt,
                max_revision_attempts=max_revision_attempts,
            )
            repository.add(
                VersionComparison(
                    workflow_run_id=workflow_run_id,
                    old_version_id=old_version_id,
                    new_version_id=new_version_id,
                    dimensions=[item.model_dump(mode="json") for item in result.dimensions],
                    overall_delta=result.overall_delta,
                    resolved_issue_codes=result.resolved_issue_codes,
                    unresolved_issue_codes=result.unresolved_issue_codes,
                    newly_introduced_issue_codes=result.newly_introduced_issue_codes,
                    decision=result.decision,
                    confidence=result.confidence,
                    rationale=result.rationale,
                )
            )
            revision.score_after = new_eval.overall_score
            revision.status = "compared"
            run = WorkflowRunRepository(session).get(workflow_run_id)
            if run is not None:
                best_id = _better_version_id(session, run.best_version_id, new_version_id)
                run.best_version_id = best_id
            return result

    def accept_version(self, workflow_run_id: int, version_id: int) -> None:
        """Atomically promote text and candidate state; safe to replay."""
        with self._session_factory.begin() as session:
            run = WorkflowRunRepository(session).get(workflow_run_id)
            version = ChapterVersionRepository(session).get(version_id)
            if run is None or version is None:
                raise EntityNotFoundError("Workflow or accepted version was not found")
            if run.status is WorkflowRunStatus.COMPLETED and run.accepted_version_id == version.id:
                return
            chapter = ChapterRepository(session).get(version.chapter_id)
            project = ProjectRepository(session).get(run.project_id)
            evaluation = EvaluationRepository(session).latest_for_version(version.id)
            if chapter is None or project is None or evaluation is None or not evaluation.passed:
                raise InvalidStateError("Only a passing evaluated version can be accepted")
            if chapter.accepted_version_id and chapter.accepted_version_id != version.id:
                previous_accepted_id = chapter.accepted_version_id
                previous = ChapterVersionRepository(session).get(chapter.accepted_version_id)
                if previous is not None:
                    previous.status = ChapterVersionStatus.SUPERSEDED
                for fact in session.scalars(
                    select(Fact).where(
                        Fact.chapter_version_id == chapter.accepted_version_id,
                        Fact.status == FactStatus.ACCEPTED,
                    )
                ):
                    fact.status = FactStatus.SUPERSEDED
                if self._memory_index is not None:
                    self._memory_index.supersede_version_in_session(session, previous_accepted_id)
            for fact in FactRepository(session).list_for_version(version.id):
                fact.status = FactStatus.ACCEPTED
            for fact in session.scalars(
                select(Fact).where(
                    Fact.workflow_run_id == workflow_run_id,
                    Fact.chapter_version_id != version.id,
                    Fact.status == FactStatus.CANDIDATE,
                )
            ):
                fact.status = FactStatus.REJECTED
            for previous_version in session.scalars(
                select(ChapterVersion).where(
                    ChapterVersion.workflow_run_id == workflow_run_id,
                    ChapterVersion.id != version.id,
                    ChapterVersion.status.not_in(
                        (
                            ChapterVersionStatus.ACCEPTED,
                            ChapterVersionStatus.SUPERSEDED,
                            ChapterVersionStatus.REJECTED,
                        )
                    ),
                )
            ):
                previous_version.status = ChapterVersionStatus.REJECTED
            for conflict in session.scalars(
                select(Conflict)
                .join(Evaluation, Conflict.evaluation_id == Evaluation.id)
                .where(
                    Evaluation.workflow_run_id == workflow_run_id,
                    Conflict.chapter_version_id != version.id,
                    Conflict.status == ConflictStatus.OPEN,
                )
            ):
                conflict.status = ConflictStatus.RESOLVED
                conflict.resolved_at = datetime.now(UTC)
            _apply_character_updates(session, project.id, version.candidate_character_updates)
            _apply_foreshadowing_updates(
                session,
                project.id,
                chapter.chapter_number,
                version.candidate_foreshadowing_updates,
            )
            version.status = ChapterVersionStatus.ACCEPTED
            version.accepted_at = datetime.now(UTC)
            chapter.accepted_version_id = version.id
            chapter.current_version_id = version.id
            chapter.version = version.version
            chapter.title = version.title
            chapter.content = version.content
            chapter.summary = version.summary
            chapter.score = evaluation.overall_score
            chapter.status = ChapterStatus.ACCEPTED
            run.current_version_id = version.id
            run.best_version_id = version.id
            run.accepted_version_id = version.id
            run.status = WorkflowRunStatus.COMPLETED
            run.current_node = "accept_version"
            run.finished_at = datetime.now(UTC)
            run.updated_at = datetime.now(UTC)
            revision = session.scalar(select(Revision).where(Revision.new_version_id == version.id))
            if revision is not None:
                revision.accepted = True
                revision.status = "accepted"
            if self._memory_index is not None:
                self._memory_index.ensure_pending_in_session(session, project.id, version.id)
        if self._memory_index is not None:
            try:
                self._memory_index.index_accepted_chapter_version(version_id)
            except Exception:
                logger.warning(
                    "memory_index_persistence_failed version_id=%s",
                    version_id,
                )
                self._memory_index.mark_version_failed(version_id, "index_persistence_error")

    def reject_revision(self, workflow_run_id: int, version_id: int) -> int:
        """Reject one candidate without deleting its text or evaluation history."""
        with self._session_factory.begin() as session:
            run = WorkflowRunRepository(session).get(workflow_run_id)
            version = ChapterVersionRepository(session).get(version_id)
            if run is None or version is None:
                raise EntityNotFoundError("Workflow or revision was not found")
            version.status = ChapterVersionStatus.REJECTED
            for fact in FactRepository(session).list_for_version(version.id):
                if fact.status is FactStatus.CANDIDATE:
                    fact.status = FactStatus.REJECTED
            revision = session.scalar(select(Revision).where(Revision.new_version_id == version.id))
            if revision is not None:
                revision.status = "rejected"
            best_id = run.best_version_id or version.parent_version_id or version.id
            run.current_version_id = best_id
            chapter = ChapterRepository(session).get(version.chapter_id)
            if chapter is not None:
                chapter.current_version_id = best_id
                chapter.status = ChapterStatus.WORKFLOW_RUNNING
            return best_id

    def mark_needs_review(self, workflow_run_id: int) -> int:
        """Expose the best text for humans without promoting its candidate facts."""
        with self._session_factory.begin() as session:
            run = WorkflowRunRepository(session).get(workflow_run_id)
            if run is None or run.best_version_id is None:
                raise InvalidStateError("Workflow has no best version for human review")
            version = ChapterVersionRepository(session).get(run.best_version_id)
            if version is None:
                raise EntityNotFoundError("Best version was not found")
            chapter = ChapterRepository(session).get(version.chapter_id)
            if chapter is None:
                raise EntityNotFoundError("Workflow chapter was not found")
            version.status = ChapterVersionStatus.NEEDS_REVIEW
            chapter.current_version_id = version.id
            chapter.version = version.version
            chapter.title = version.title
            chapter.content = version.content
            chapter.summary = version.summary
            chapter.status = ChapterStatus.NEEDS_HUMAN_REVIEW
            run.current_version_id = version.id
            run.status = WorkflowRunStatus.COMPLETED_NEEDS_REVIEW
            run.current_node = "mark_needs_human_review"
            run.finished_at = datetime.now(UTC)
            run.updated_at = datetime.now(UTC)
            for fact in session.scalars(
                select(Fact).where(
                    Fact.workflow_run_id == workflow_run_id,
                    Fact.status == FactStatus.CANDIDATE,
                )
            ):
                fact.status = FactStatus.REJECTED
            for other_version in session.scalars(
                select(ChapterVersion).where(
                    ChapterVersion.workflow_run_id == workflow_run_id,
                    ChapterVersion.id != version.id,
                    ChapterVersion.status.not_in(
                        (
                            ChapterVersionStatus.ACCEPTED,
                            ChapterVersionStatus.SUPERSEDED,
                            ChapterVersionStatus.REJECTED,
                        )
                    ),
                )
            ):
                other_version.status = ChapterVersionStatus.REJECTED
            return version.id


def _word_count(content: str) -> int:
    cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", content))
    words = len(re.findall(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*", content))
    return cjk + words


def _evaluation_snapshot(evaluation: Evaluation) -> EvaluationSnapshot:
    issue_codes = [item.code for item in evaluation.issue_records]
    issue_codes.extend(item.rule_code for item in evaluation.conflicts)
    return EvaluationSnapshot(
        evaluation_id=evaluation.id,
        version_id=evaluation.chapter_version_id,
        final_score=evaluation.overall_score,
        consistency_score=evaluation.consistency_score,
        outline_adherence_score=evaluation.outline_adherence_score,
        critical_conflicts=sum(
            item.severity is ConflictSeverity.CRITICAL for item in evaluation.conflicts
        ),
        high_conflicts=sum(item.severity is ConflictSeverity.HIGH for item in evaluation.conflicts),
        blocking_reasons=list(evaluation.blocking_reasons),
        issue_codes=sorted(set(issue_codes)),
        passed=evaluation.passed,
        recommended_action=cast(
            Literal["accept", "revise", "human_review", "reject"],
            evaluation.recommended_action,
        ),
    )


def _better_version_id(session: object, current_best_id: int | None, candidate_id: int) -> int:
    from sqlalchemy.orm import Session

    if not isinstance(session, Session):
        return candidate_id
    candidate = EvaluationRepository(session).latest_for_version(candidate_id)
    current = (
        EvaluationRepository(session).latest_for_version(current_best_id)
        if current_best_id is not None
        else None
    )
    if candidate is None:
        return current_best_id or candidate_id
    if current is None:
        return candidate_id
    candidate_rank = _evaluation_rank(candidate)
    current_rank = _evaluation_rank(current)
    if candidate_rank > current_rank:
        return candidate_id
    assert current_best_id is not None
    return current_best_id


def _evaluation_rank(evaluation: Evaluation) -> tuple[int, int, float, float, float, int]:
    critical = sum(item.severity is ConflictSeverity.CRITICAL for item in evaluation.conflicts)
    high = sum(item.severity is ConflictSeverity.HIGH for item in evaluation.conflicts)
    return (
        -critical,
        -len(evaluation.blocking_reasons),
        evaluation.overall_score,
        evaluation.consistency_score,
        evaluation.outline_adherence_score,
        -high,
    )


def _comparison_result(comparison: VersionComparison) -> VersionComparisonResult:
    return VersionComparisonResult(
        old_version_id=comparison.old_version_id,
        new_version_id=comparison.new_version_id,
        dimensions=[ComparisonDimension.model_validate(item) for item in comparison.dimensions],
        overall_delta=comparison.overall_delta,
        resolved_issue_codes=list(comparison.resolved_issue_codes),
        unresolved_issue_codes=list(comparison.unresolved_issue_codes),
        newly_introduced_issue_codes=list(comparison.newly_introduced_issue_codes),
        decision=cast(
            Literal["accept_new", "keep_old_retry", "keep_old_stop", "human_review"],
            comparison.decision,
        ),
        confidence=comparison.confidence,
        rationale=comparison.rationale,
    )


def _apply_character_updates(
    session: object, project_id: int, updates: list[dict[str, object]]
) -> None:
    from sqlalchemy.orm import Session

    if not isinstance(session, Session):
        return
    characters = {
        item.name: item for item in CharacterRepository(session).list_for_project(project_id)
    }
    for update in updates:
        character = characters.get(str(update.get("character_name", "")))
        if character is not None and update.get("field") == "current_state":
            character.current_state = str(update.get("value", character.current_state))


def _apply_foreshadowing_updates(
    session: object,
    project_id: int,
    chapter_number: int,
    updates: list[dict[str, object]],
) -> None:
    from sqlalchemy.orm import Session

    if not isinstance(session, Session):
        return
    repository = ForeshadowingRepository(session)
    for update in updates:
        raw_id = update.get("foreshadowing_id")
        record = repository.get(int(raw_id)) if isinstance(raw_id, int) else None
        action = str(update.get("action", ""))
        if record is not None and record.project_id != project_id:
            continue
        if action == "setup" and record is None:
            repository.add(
                Foreshadowing(
                    project_id=project_id,
                    setup_chapter=chapter_number,
                    expected_payoff_chapter=chapter_number,
                    description=str(update.get("description", "")),
                    status=ForeshadowingStatus.OPEN,
                )
            )
        elif record is not None and action == "resolve":
            record.status = ForeshadowingStatus.RESOLVED
            record.payoff_chapter = chapter_number
        elif record is not None and action == "advance":
            record.status = ForeshadowingStatus.OPEN
