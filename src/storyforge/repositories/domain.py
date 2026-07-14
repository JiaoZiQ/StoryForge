"""Typed repositories for each StoryForge domain entity."""

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from storyforge.enums import (
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    FactStatus,
    ForeshadowingStatus,
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
from storyforge.repositories.base import Repository


class ProjectRepository(Repository[Project]):
    """Persistence operations for projects."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Project)


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


class ForeshadowingRepository(Repository[Foreshadowing]):
    """Persistence operations for foreshadowing records."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Foreshadowing)

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


class EvaluationIssueRepository(Repository[EvaluationIssue]):
    """Persistence operations for normalized evaluation issues."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, EvaluationIssue)

    def add_many(self, issues: Iterable[EvaluationIssue]) -> None:
        """Stage normalized issues in the caller-owned transaction."""
        self.session.add_all(issues)


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


class RevisionRepository(Repository[Revision]):
    """Persistence operations for revisions."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Revision)


class WorkflowRunRepository(Repository[WorkflowRun]):
    """Persistence operations for workflow runs."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, WorkflowRun)

    def get_by_thread_id(self, thread_id: str) -> WorkflowRun | None:
        """Return the durable run associated with one LangGraph thread."""
        return self.session.scalar(select(WorkflowRun).where(WorkflowRun.thread_id == thread_id))


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
