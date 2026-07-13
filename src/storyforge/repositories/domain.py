"""Typed repositories for each StoryForge domain entity."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from storyforge.models import (
    Chapter,
    Character,
    Evaluation,
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


class LocationRepository(Repository[Location]):
    """Persistence operations for locations."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Location)


class StoryRuleRepository(Repository[StoryRule]):
    """Persistence operations for story rules."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, StoryRule)


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


class FactRepository(Repository[Fact]):
    """Persistence operations for structured facts."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Fact)


class ForeshadowingRepository(Repository[Foreshadowing]):
    """Persistence operations for foreshadowing records."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Foreshadowing)


class EvaluationRepository(Repository[Evaluation]):
    """Persistence operations for evaluations."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Evaluation)


class RevisionRepository(Repository[Revision]):
    """Persistence operations for revisions."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Revision)


class WorkflowRunRepository(Repository[WorkflowRun]):
    """Persistence operations for workflow runs."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, WorkflowRun)
