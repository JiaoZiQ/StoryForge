"""Repository interfaces for StoryForge persistence."""

from storyforge.repositories.base import Repository
from storyforge.repositories.domain import (
    ChapterRepository,
    ChapterVersionRepository,
    CharacterRepository,
    EvaluationRepository,
    FactRepository,
    ForeshadowingRepository,
    LocationRepository,
    ProjectRepository,
    RevisionRepository,
    StoryRuleRepository,
    WorkflowRunRepository,
)

__all__ = [
    "ChapterRepository",
    "ChapterVersionRepository",
    "CharacterRepository",
    "EvaluationRepository",
    "FactRepository",
    "ForeshadowingRepository",
    "LocationRepository",
    "ProjectRepository",
    "Repository",
    "RevisionRepository",
    "StoryRuleRepository",
    "WorkflowRunRepository",
]
