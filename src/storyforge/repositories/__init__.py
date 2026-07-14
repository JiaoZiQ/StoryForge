"""Repository interfaces for StoryForge persistence."""

from storyforge.repositories.base import Repository
from storyforge.repositories.domain import (
    ChapterRepository,
    ChapterVersionRepository,
    CharacterRepository,
    ConflictRepository,
    EvaluationIssueRepository,
    EvaluationRepository,
    FactRepository,
    ForeshadowingRepository,
    LocationRepository,
    ProjectRepository,
    RevisionRepository,
    StoryRuleRepository,
    VersionComparisonRepository,
    WorkflowEventRepository,
    WorkflowRunRepository,
)

__all__ = [
    "ChapterRepository",
    "ChapterVersionRepository",
    "CharacterRepository",
    "ConflictRepository",
    "EvaluationIssueRepository",
    "EvaluationRepository",
    "FactRepository",
    "ForeshadowingRepository",
    "LocationRepository",
    "ProjectRepository",
    "Repository",
    "RevisionRepository",
    "StoryRuleRepository",
    "VersionComparisonRepository",
    "WorkflowEventRepository",
    "WorkflowRunRepository",
]
