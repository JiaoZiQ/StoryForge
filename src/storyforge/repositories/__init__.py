"""Repository interfaces for StoryForge persistence."""

from storyforge.repositories.base import PageSlice, Repository
from storyforge.repositories.domain import (
    ChapterRepository,
    ChapterVersionRepository,
    CharacterRepository,
    ConflictRepository,
    DemoAuditRepository,
    EvaluationIssueRepository,
    EvaluationRepository,
    FactRepository,
    ForeshadowingRepository,
    LocationRepository,
    ProjectRepository,
    RevisionRepository,
    StoryRuleRepository,
    SystemRepository,
    VersionComparisonRepository,
    WorkflowEventRepository,
    WorkflowRunRepository,
)

__all__ = [
    "ChapterRepository",
    "ChapterVersionRepository",
    "CharacterRepository",
    "ConflictRepository",
    "DemoAuditRepository",
    "EvaluationIssueRepository",
    "EvaluationRepository",
    "FactRepository",
    "ForeshadowingRepository",
    "LocationRepository",
    "PageSlice",
    "ProjectRepository",
    "Repository",
    "RevisionRepository",
    "StoryRuleRepository",
    "SystemRepository",
    "VersionComparisonRepository",
    "WorkflowEventRepository",
    "WorkflowRunRepository",
]
