"""Typed repositories for each StoryForge domain entity."""

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from storyforge.enums import (
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    FactStatus,
    ForeshadowingStatus,
    WorkflowRunStatus,
)
from storyforge.models import (
    Chapter,
    ChapterVersion,
    Character,
    Conflict,
    Evaluation,
    EvaluationIssue,
    Fact,
    Foreshadowing,
    Location,
    Project,
    Revision,
    StoryRule,
    VersionComparison,
    WorkflowEvent,
    WorkflowRun,
)
from storyforge.repositories.base import PageSlice, Repository


class SystemRepository:
    """Small infrastructure probes used by readiness checks."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def ping(self) -> None:
        self.session.execute(text("SELECT 1"))

    def migration_revision(self) -> str:
        value = self.session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        return str(value)


class DemoAuditRepository:
    """Aggregate-only checks used by the offline milestone demonstration."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def duplicate_version_count(self, project_id: int) -> int:
        duplicates = (
            select(ChapterVersion.idempotency_key, func.count(ChapterVersion.id).label("amount"))
            .join(Chapter, ChapterVersion.chapter_id == Chapter.id)
            .where(
                Chapter.project_id == project_id,
                ChapterVersion.idempotency_key.is_not(None),
            )
            .group_by(ChapterVersion.idempotency_key)
            .having(func.count(ChapterVersion.id) > 1)
            .subquery()
        )
        return self.session.scalar(select(func.count()).select_from(duplicates)) or 0

    def duplicate_evaluation_count(self, project_id: int) -> int:
        duplicates = (
            select(Evaluation.idempotency_key, func.count(Evaluation.id).label("amount"))
            .where(
                Evaluation.project_id == project_id,
                Evaluation.idempotency_key.is_not(None),
            )
            .group_by(Evaluation.idempotency_key)
            .having(func.count(Evaluation.id) > 1)
            .subquery()
        )
        return self.session.scalar(select(func.count()).select_from(duplicates)) or 0

    def duplicate_fact_count(self, project_id: int) -> int:
        duplicates = (
            select(
                Fact.chapter_version_id,
                Fact.normalized_hash,
                func.count(Fact.id).label("amount"),
            )
            .where(Fact.project_id == project_id)
            .group_by(Fact.chapter_version_id, Fact.normalized_hash)
            .having(func.count(Fact.id) > 1)
            .subquery()
        )
        return self.session.scalar(select(func.count()).select_from(duplicates)) or 0

    def duplicate_conflict_count(self, project_id: int) -> int:
        """Count repeated rule findings inside the same immutable evaluation."""
        duplicates = (
            select(
                Conflict.evaluation_id,
                Conflict.chapter_version_id,
                Conflict.rule_code,
                Conflict.subject,
                Conflict.new_evidence,
                func.count(Conflict.id).label("amount"),
            )
            .where(Conflict.project_id == project_id)
            .group_by(
                Conflict.evaluation_id,
                Conflict.chapter_version_id,
                Conflict.rule_code,
                Conflict.subject,
                Conflict.new_evidence,
            )
            .having(func.count(Conflict.id) > 1)
            .subquery()
        )
        return self.session.scalar(select(func.count()).select_from(duplicates)) or 0


class ProjectRepository(Repository[Project]):
    """Persistence operations for projects."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Project)

    def page_filtered(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        genre: str | None = None,
        language: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        search: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> PageSlice[Project]:
        """Filter and sort projects using a strict column whitelist."""
        sort_columns = {
            "id": Project.id,
            "title": Project.title,
            "created_at": Project.created_at,
            "updated_at": Project.updated_at,
        }
        if sort not in sort_columns or order not in {"asc", "desc"}:
            raise ValueError("Unsupported project sort or order")
        statement = select(Project)
        if status is not None:
            statement = statement.where(Project.status == status)
        if genre is not None:
            statement = statement.where(Project.genre == genre)
        if language is not None:
            statement = statement.where(Project.language == language)
        if created_from is not None:
            statement = statement.where(Project.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(Project.created_at <= created_to)
        if search is not None:
            pattern = f"%{search}%"
            statement = statement.where(
                or_(Project.title.ilike(pattern), Project.premise.ilike(pattern))
            )
        column = sort_columns[sort]
        statement = statement.order_by(
            column.asc() if order == "asc" else column.desc(), Project.id
        )
        return self.paginate(statement, page=page, page_size=page_size)

    def has_plan_or_content(self, project_id: int) -> bool:
        """Return whether deletion would remove planned or generated chapter data."""
        return bool(
            self.session.scalar(
                select(func.count(Chapter.id)).where(Chapter.project_id == project_id)
            )
        )

    def related_counts(self, project_id: int) -> tuple[int, int]:
        """Return chapter and workflow counts for one project detail projection."""
        chapter_count = (
            self.session.scalar(
                select(func.count(Chapter.id)).where(Chapter.project_id == project_id)
            )
            or 0
        )
        workflow_count = (
            self.session.scalar(
                select(func.count(WorkflowRun.id)).where(WorkflowRun.project_id == project_id)
            )
            or 0
        )
        return chapter_count, workflow_count


class CharacterRepository(Repository[Character]):
    """Persistence operations for characters."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Character)

    def list_for_project(self, project_id: int) -> list[Character]:
        """Return a project's characters in stable ID order."""
        return list(
            self.session.scalars(
                select(Character).where(Character.project_id == project_id).order_by(Character.id)
            )
        )


class LocationRepository(Repository[Location]):
    """Persistence operations for locations."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Location)

    def list_for_project(self, project_id: int) -> list[Location]:
        """Return a project's locations in stable ID order."""
        return list(
            self.session.scalars(
                select(Location).where(Location.project_id == project_id).order_by(Location.id)
            )
        )


class StoryRuleRepository(Repository[StoryRule]):
    """Persistence operations for story rules."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, StoryRule)

    def list_active_for_project(self, project_id: int) -> list[StoryRule]:
        """Return active project rules in stable ID order."""
        return list(
            self.session.scalars(
                select(StoryRule)
                .where(StoryRule.project_id == project_id, StoryRule.active.is_(True))
                .order_by(StoryRule.id)
            )
        )


class ChapterRepository(Repository[Chapter]):
    """Persistence operations for chapters."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Chapter)

    def get_by_number(self, project_id: int, chapter_number: int) -> Chapter | None:
        """Return a chapter by its project-scoped number."""
        statement = select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
        )
        return self.session.scalar(statement)

    def list_for_project(self, project_id: int) -> list[Chapter]:
        """Return project chapters in narrative order."""
        statement = (
            select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number)
        )
        return list(self.session.scalars(statement))

    def page_for_project(
        self,
        project_id: int,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        has_content: bool | None = None,
        passed: bool | None = None,
        min_score: float | None = None,
        max_score: float | None = None,
        sort: str = "chapter_number",
        order: str = "asc",
    ) -> PageSlice[Chapter]:
        """Return a filtered chapter page without loading chapter bodies separately."""
        sort_columns = {
            "chapter_number": Chapter.chapter_number,
            "status": Chapter.status,
            "score": Chapter.score,
            "updated_at": Chapter.updated_at,
        }
        if sort not in sort_columns or order not in {"asc", "desc"}:
            raise ValueError("Unsupported chapter sort or order")
        statement = select(Chapter).where(Chapter.project_id == project_id)
        if status is not None:
            statement = statement.where(Chapter.status == status)
        if has_content is not None:
            statement = statement.where(
                func.length(func.trim(Chapter.content)) > 0
                if has_content
                else func.length(func.trim(Chapter.content)) == 0
            )
        if passed is not None:
            passing = Chapter.status.in_(("accepted", "evaluated_passed"))
            statement = statement.where(passing if passed else ~passing)
        if min_score is not None:
            statement = statement.where(Chapter.score >= min_score)
        if max_score is not None:
            statement = statement.where(Chapter.score <= max_score)
        column = sort_columns[sort]
        statement = statement.order_by(
            column.asc() if order == "asc" else column.desc(), Chapter.chapter_number
        )
        return self.paginate(statement, page=page, page_size=page_size)

    def count_versions(self, chapter_id: int) -> int:
        return (
            self.session.scalar(
                select(func.count(ChapterVersion.id)).where(ChapterVersion.chapter_id == chapter_id)
            )
            or 0
        )

    def count_conflicts(self, chapter_id: int) -> int:
        return (
            self.session.scalar(
                select(func.count(Conflict.id)).where(Conflict.chapter_id == chapter_id)
            )
            or 0
        )


class FactRepository(Repository[Fact]):
    """Persistence operations for structured facts."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Fact)

    def list_known_before(self, project_id: int, chapter_number: int) -> list[Fact]:
        """Return facts extracted only from earlier chapters and valid now."""
        statement = (
            select(Fact)
            .join(Chapter, Fact.chapter_id == Chapter.id)
            .where(
                Fact.project_id == project_id,
                Fact.status == FactStatus.ACCEPTED,
                Chapter.chapter_number < chapter_number,
                Fact.valid_from_chapter <= chapter_number,
                (Fact.valid_to_chapter.is_(None)) | (Fact.valid_to_chapter >= chapter_number),
            )
            .order_by(Fact.confidence.desc(), Fact.id)
        )
        return list(self.session.scalars(statement))

    def list_for_version(
        self, chapter_version_id: int, *, status: FactStatus | None = None
    ) -> list[Fact]:
        """Return version-scoped facts without silently promoting candidates."""
        statement = select(Fact).where(Fact.chapter_version_id == chapter_version_id)
        if status is not None:
            statement = statement.where(Fact.status == status)
        return list(self.session.scalars(statement.order_by(Fact.id)))

    def page_for_project(
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
    ) -> PageSlice[Fact]:
        """Page version-scoped facts with canonical and temporal filtering."""
        statement = (
            select(Fact)
            .join(Chapter, Fact.chapter_id == Chapter.id)
            .where(
                Fact.project_id == project_id,
                Fact.status == status,
            )
        )
        if chapter_number is not None:
            statement = statement.where(Chapter.chapter_number == chapter_number)
        if subject is not None:
            statement = statement.where(Fact.subject == subject)
        if predicate is not None:
            statement = statement.where(Fact.predicate == predicate)
        if version_id is not None:
            statement = statement.where(Fact.chapter_version_id == version_id)
        if valid_at_chapter is not None:
            statement = statement.where(
                Chapter.chapter_number < valid_at_chapter,
                Fact.valid_from_chapter <= valid_at_chapter,
                or_(Fact.valid_to_chapter.is_(None), Fact.valid_to_chapter >= valid_at_chapter),
            )
        if confidence_min is not None:
            statement = statement.where(Fact.confidence >= confidence_min)
        return self.paginate(statement.order_by(Fact.id), page=page, page_size=page_size)


class ForeshadowingRepository(Repository[Foreshadowing]):
    """Persistence operations for foreshadowing records."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Foreshadowing)

    def list_for_project(self, project_id: int) -> list[Foreshadowing]:
        return list(
            self.session.scalars(
                select(Foreshadowing)
                .where(Foreshadowing.project_id == project_id)
                .order_by(Foreshadowing.id)
            )
        )

    def list_active_before(self, project_id: int, chapter_number: int) -> list[Foreshadowing]:
        """Return setups already visible to the current chapter."""
        statement = (
            select(Foreshadowing)
            .where(
                Foreshadowing.project_id == project_id,
                Foreshadowing.setup_chapter < chapter_number,
                Foreshadowing.status == ForeshadowingStatus.OPEN,
            )
            .order_by(Foreshadowing.expected_payoff_chapter, Foreshadowing.id)
        )
        return list(self.session.scalars(statement))


class ChapterVersionRepository(Repository[ChapterVersion]):
    """Persistence operations for immutable chapter snapshots."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ChapterVersion)

    def next_version(self, chapter_id: int) -> int:
        """Return the next immutable text version number for a chapter."""
        current = self.session.scalar(
            select(func.max(ChapterVersion.version)).where(ChapterVersion.chapter_id == chapter_id)
        )
        return (current or 0) + 1

    def get_by_idempotency_key(self, key: str) -> ChapterVersion | None:
        """Return a previously created version for node replay."""
        return self.session.scalar(
            select(ChapterVersion).where(ChapterVersion.idempotency_key == key)
        )

    def list_for_chapter(self, chapter_id: int) -> list[ChapterVersion]:
        """Return all immutable versions in numeric order."""
        return list(
            self.session.scalars(
                select(ChapterVersion)
                .where(ChapterVersion.chapter_id == chapter_id)
                .order_by(ChapterVersion.version)
            )
        )

    def get_for_chapter(self, chapter_id: int, version_id: int) -> ChapterVersion | None:
        return self.session.scalar(
            select(ChapterVersion).where(
                ChapterVersion.chapter_id == chapter_id,
                ChapterVersion.id == version_id,
            )
        )

    def page_for_chapter(
        self, chapter_id: int, *, page: int, page_size: int
    ) -> PageSlice[ChapterVersion]:
        statement = (
            select(ChapterVersion)
            .where(ChapterVersion.chapter_id == chapter_id)
            .order_by(ChapterVersion.version.desc())
        )
        return self.paginate(statement, page=page, page_size=page_size)


class EvaluationRepository(Repository[Evaluation]):
    """Persistence operations for evaluations."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Evaluation)

    def next_version(self, chapter_id: int) -> int:
        """Return the next immutable evaluation version for a chapter."""
        current = self.session.scalar(
            select(func.max(Evaluation.evaluation_version)).where(
                Evaluation.chapter_id == chapter_id
            )
        )
        return (current or 0) + 1

    def list_for_chapter(self, chapter_id: int) -> list[Evaluation]:
        """Return a chapter's evaluation history in version order."""
        statement = (
            select(Evaluation)
            .where(Evaluation.chapter_id == chapter_id)
            .order_by(Evaluation.evaluation_version)
        )
        return list(self.session.scalars(statement))

    def get_by_idempotency_key(self, key: str) -> Evaluation | None:
        """Return an evaluation already persisted for an idempotent node replay."""
        return self.session.scalar(select(Evaluation).where(Evaluation.idempotency_key == key))

    def latest_for_version(self, chapter_version_id: int) -> Evaluation | None:
        """Return the most recent complete attempt for a concrete text version."""
        return self.session.scalar(
            select(Evaluation)
            .where(Evaluation.chapter_version_id == chapter_version_id)
            .order_by(Evaluation.evaluation_version.desc())
            .limit(1)
        )

    def page_for_chapter(
        self,
        chapter_id: int,
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
    ) -> PageSlice[Evaluation]:
        sort_columns = {
            "created_at": Evaluation.created_at,
            "final_score": Evaluation.overall_score,
            "evaluation_version": Evaluation.evaluation_version,
        }
        if sort not in sort_columns or order not in {"asc", "desc"}:
            raise ValueError("Unsupported evaluation sort or order")
        statement = select(Evaluation).where(Evaluation.chapter_id == chapter_id)
        if version_id is not None:
            statement = statement.where(Evaluation.chapter_version_id == version_id)
        if passed is not None:
            statement = statement.where(Evaluation.passed.is_(passed))
        if recommended_action is not None:
            statement = statement.where(Evaluation.recommended_action == recommended_action)
        if min_score is not None:
            statement = statement.where(Evaluation.overall_score >= min_score)
        if max_score is not None:
            statement = statement.where(Evaluation.overall_score <= max_score)
        column = sort_columns[sort]
        statement = statement.order_by(
            column.asc() if order == "asc" else column.desc(), Evaluation.id.desc()
        )
        return self.paginate(statement, page=page, page_size=page_size)


class EvaluationIssueRepository(Repository[EvaluationIssue]):
    """Persistence operations for normalized evaluation issues."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, EvaluationIssue)

    def add_many(self, issues: Iterable[EvaluationIssue]) -> None:
        """Stage normalized issues in the caller-owned transaction."""
        self.session.add_all(issues)

    def list_for_evaluation(self, evaluation_id: int) -> list[EvaluationIssue]:
        """Return normalized issues in stable persistence order."""
        return list(
            self.session.scalars(
                select(EvaluationIssue)
                .where(EvaluationIssue.evaluation_id == evaluation_id)
                .order_by(EvaluationIssue.id)
            )
        )


class ConflictRepository(Repository[Conflict]):
    """Persistence and filtering for consistency conflicts."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Conflict)

    def add_many(self, conflicts: Iterable[Conflict]) -> None:
        """Stage conflicts in the caller-owned transaction."""
        self.session.add_all(conflicts)

    def list_for_project(
        self,
        project_id: int,
        *,
        chapter_id: int | None = None,
        severity: ConflictSeverity | None = None,
        conflict_type: ConflictType | None = None,
        status: ConflictStatus | None = None,
    ) -> list[Conflict]:
        """Return stable, optionally filtered conflict records."""
        statement = select(Conflict).where(Conflict.project_id == project_id)
        if chapter_id is not None:
            statement = statement.where(Conflict.chapter_id == chapter_id)
        if severity is not None:
            statement = statement.where(Conflict.severity == severity)
        if conflict_type is not None:
            statement = statement.where(Conflict.conflict_type == conflict_type)
        if status is not None:
            statement = statement.where(Conflict.status == status)
        return list(self.session.scalars(statement.order_by(Conflict.id)))

    def page_for_project(
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
    ) -> PageSlice[Conflict]:
        statement = (
            select(Conflict)
            .join(Chapter, Conflict.chapter_id == Chapter.id)
            .where(Conflict.project_id == project_id)
        )
        if chapter_number is not None:
            statement = statement.where(Chapter.chapter_number == chapter_number)
        if version_id is not None:
            statement = statement.where(Conflict.chapter_version_id == version_id)
        if severity is not None:
            statement = statement.where(Conflict.severity == severity)
        if conflict_type is not None:
            statement = statement.where(Conflict.conflict_type == conflict_type)
        if status is not None:
            statement = statement.where(Conflict.status == status)
        if rule_code is not None:
            statement = statement.where(Conflict.rule_code == rule_code)
        return self.paginate(statement.order_by(Conflict.id), page=page, page_size=page_size)


class RevisionRepository(Repository[Revision]):
    """Persistence operations for revisions."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Revision)

    def get_for_new_version(self, chapter_version_id: int) -> Revision | None:
        """Return the revision metadata that produced a concrete version."""
        return self.session.scalar(
            select(Revision)
            .where(Revision.new_version_id == chapter_version_id)
            .order_by(Revision.id.desc())
            .limit(1)
        )


class WorkflowRunRepository(Repository[WorkflowRun]):
    """Persistence operations for workflow runs."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, WorkflowRun)

    def get_by_thread_id(self, thread_id: str) -> WorkflowRun | None:
        """Return the durable run associated with one LangGraph thread."""
        return self.session.scalar(select(WorkflowRun).where(WorkflowRun.thread_id == thread_id))

    def latest_for_chapter(self, chapter_id: int) -> WorkflowRun | None:
        """Return the newest workflow audit record for a chapter."""
        return self.session.scalar(
            select(WorkflowRun)
            .where(WorkflowRun.chapter_id == chapter_id)
            .order_by(WorkflowRun.id.desc())
            .limit(1)
        )

    def active_for_project(self, project_id: int) -> WorkflowRun | None:
        """Return an in-flight run that makes aggregate replanning unsafe."""
        return self.session.scalar(
            select(WorkflowRun)
            .where(
                WorkflowRun.project_id == project_id,
                WorkflowRun.status.in_(
                    (
                        WorkflowRunStatus.PENDING,
                        WorkflowRunStatus.RUNNING,
                        WorkflowRunStatus.PAUSED,
                    )
                ),
            )
            .order_by(WorkflowRun.id.desc())
            .limit(1)
        )

    def page_for_project(
        self, project_id: int, *, page: int, page_size: int
    ) -> PageSlice[WorkflowRun]:
        statement = (
            select(WorkflowRun)
            .where(WorkflowRun.project_id == project_id)
            .order_by(WorkflowRun.id.desc())
        )
        return self.paginate(statement, page=page, page_size=page_size)


class WorkflowEventRepository(Repository[WorkflowEvent]):
    """Persistence operations for content-free workflow audit events."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, WorkflowEvent)

    def list_for_run(self, workflow_run_id: int) -> list[WorkflowEvent]:
        """Return audit events in creation order."""
        return list(
            self.session.scalars(
                select(WorkflowEvent)
                .where(WorkflowEvent.workflow_run_id == workflow_run_id)
                .order_by(WorkflowEvent.id)
            )
        )

    def page_for_run(
        self, workflow_run_id: int, *, page: int, page_size: int
    ) -> PageSlice[WorkflowEvent]:
        statement = (
            select(WorkflowEvent)
            .where(WorkflowEvent.workflow_run_id == workflow_run_id)
            .order_by(WorkflowEvent.id)
        )
        return self.paginate(statement, page=page, page_size=page_size)


class VersionComparisonRepository(Repository[VersionComparison]):
    """Persistence operations for deterministic version comparisons."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, VersionComparison)

    def get_for_new_version(
        self, workflow_run_id: int, new_version_id: int
    ) -> VersionComparison | None:
        """Return a comparison already created for node replay."""
        return self.session.scalar(
            select(VersionComparison).where(
                VersionComparison.workflow_run_id == workflow_run_id,
                VersionComparison.new_version_id == new_version_id,
            )
        )

    def list_for_run(self, workflow_run_id: int) -> list[VersionComparison]:
        """Return comparisons in persisted order."""
        return list(
            self.session.scalars(
                select(VersionComparison)
                .where(VersionComparison.workflow_run_id == workflow_run_id)
                .order_by(VersionComparison.id)
            )
        )
