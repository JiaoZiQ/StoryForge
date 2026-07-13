"""Typed evidence, conflict, and result models for consistency checks."""

from pydantic import Field

from storyforge.enums import (
    ConflictSeverity,
    ConflictType,
    ForeshadowingStatus,
)
from storyforge.evaluation.models import TenScore
from storyforge.schemas.base import Confidence, EntityId, NonNegativeInt, PositiveInt, RequestModel


class FactEvidence(RequestModel):
    """Raw fact evidence preserved alongside normalized comparison values."""

    fact_id: EntityId | None = None
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    fact_type: str = "event"
    confidence: Confidence = 1
    source_quote: str = ""
    chapter_number: PositiveInt
    valid_from_chapter: PositiveInt
    valid_to_chapter: PositiveInt | None = None


class CharacterStateUpdateEvidence(RequestModel):
    """A structured character state update from generation."""

    character_name: str
    field: str
    value: str
    confidence: Confidence
    source_quote: str = ""


class CharacterEvidence(RequestModel):
    """Local-only character state and knowledge boundary."""

    name: str
    current_state: str
    knowledge: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)


class StoryRuleEvidence(RequestModel):
    """Story rule with optional mechanically matchable metadata."""

    rule_id: EntityId
    category: str
    statement: str
    structured_metadata: dict[str, object] = Field(default_factory=dict)


class ChapterOutlineEvidence(RequestModel):
    """Current chapter requirements relevant to mechanical consistency."""

    key_events: list[str] = Field(default_factory=list)
    forbidden_reveals: list[str] = Field(default_factory=list)
    payoff_foreshadowing: list[str] = Field(default_factory=list)


class ForeshadowingEvidence(RequestModel):
    """Persisted foreshadowing state visible at evaluation time."""

    foreshadowing_id: EntityId
    description: str
    setup_chapter: PositiveInt
    expected_payoff_chapter: PositiveInt
    payoff_chapter: PositiveInt | None = None
    status: ForeshadowingStatus


class ForeshadowingUpdateEvidence(RequestModel):
    """Structured setup/payoff action extracted from the current chapter."""

    action: str
    description: str
    foreshadowing_id: EntityId | None = None
    confidence: Confidence = 1


class ChapterSummaryEvidence(RequestModel):
    """An earlier generated chapter summary."""

    chapter_number: PositiveInt
    summary: str


class ConsistencyConflict(RequestModel):
    """Explainable conflict ready for persistence."""

    conflict_type: ConflictType
    severity: ConflictSeverity
    subject: str = Field(min_length=1)
    description: str = Field(min_length=1)
    new_evidence: str = Field(min_length=1)
    existing_evidence: str | None = None
    existing_fact_id: EntityId | None = None
    chapter_number: PositiveInt
    suggested_resolution: str = Field(min_length=1)
    confidence: Confidence
    rule_code: str = Field(min_length=1, max_length=100)


class ConsistencyCheckRequest(RequestModel):
    """Complete local evidence bundle for one chapter check."""

    project_id: EntityId
    chapter_id: EntityId
    chapter_number: PositiveInt
    content: str
    new_facts: list[FactEvidence] = Field(default_factory=list)
    character_updates: list[CharacterStateUpdateEvidence] = Field(default_factory=list)
    historical_facts: list[FactEvidence] = Field(default_factory=list)
    characters: list[CharacterEvidence] = Field(default_factory=list)
    story_rules: list[StoryRuleEvidence] = Field(default_factory=list)
    outline: ChapterOutlineEvidence
    active_foreshadowing: list[ForeshadowingEvidence] = Field(default_factory=list)
    foreshadowing_updates: list[ForeshadowingUpdateEvidence] = Field(default_factory=list)
    previous_summaries: list[ChapterSummaryEvidence] = Field(default_factory=list)


class ConsistencyCheckResult(RequestModel):
    """Bounded consistency score and severity summary."""

    score: TenScore
    conflicts: list[ConsistencyConflict] = Field(default_factory=list)
    checked_rule_count: NonNegativeInt
    critical_count: NonNegativeInt
    high_count: NonNegativeInt
    medium_count: NonNegativeInt
    low_count: NonNegativeInt
    checker_version: str
