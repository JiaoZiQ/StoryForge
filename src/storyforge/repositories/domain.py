"""Typed repositories for each StoryForge domain entity."""

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from storyforge.enums import (
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
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
                Chapter.chapter_number < chapter_number,
                Fact.valid_from_chapter <= chapter_number,
                (Fact.valid_to_chapter.is_(None)) | (Fact.valid_to_chapter >= chapter_number),
            )
            .order_by(Fact.confidence.desc(), Fact.id)
        )
        return list(self.session.scalars(statement))


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
