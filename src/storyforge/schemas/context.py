"""Minimal, typed chapter context models used by WriterAgent."""

from pydantic import Field

from storyforge.schemas.base import (
    Confidence,
    EntityId,
    LongText,
    NonNegativeInt,
    PositiveInt,
    RequestModel,
    ShortText,
)


class ContextBuildRequest(RequestModel):
    """Request for a bounded, leak-free writer context."""

    project_id: EntityId
    chapter_number: PositiveInt
    max_context_chars: PositiveInt = 24_000
    recent_chapter_limit: NonNegativeInt = 3
    max_characters: PositiveInt = 8


class ProjectContext(RequestModel):
    """High-level story direction relevant to every chapter."""

    title: ShortText
    genre: str
    premise: LongText
    themes: list[str]
    world_summary: str
    central_conflict: str
    style_guide: str
    language: str
    tone: str | None
    audience: str | None


class ChapterOutlineContext(RequestModel):
    """Current chapter plan, which the budgeter never removes."""

    chapter_number: PositiveInt
    title: ShortText
    objective: LongText
    summary: LongText
    key_events: list[str]
    participating_characters: list[str]
    locations: list[str]
    required_facts: list[str]
    forbidden_reveals: list[str]
    setup_foreshadowing: list[str]
    payoff_foreshadowing: list[str]
    ending_hook: LongText


class CharacterContext(RequestModel):
    """Writer-visible character data with author-only secrets excluded."""

    name: ShortText
    role: str
    description: str
    goals: list[str]
    personality: list[str]
    speech_style: str
    current_state: str


class LocationContext(RequestModel):
    """Writer-visible location data."""

    name: ShortText
    description: str
    rules: list[str]


class RuleContext(RequestModel):
    """One active story rule."""

    category: str
    statement: str


class RecentChapterContext(RequestModel):
    """Summary of an earlier, already-generated chapter."""

    chapter_number: PositiveInt
    title: str
    summary: LongText


class FactContext(RequestModel):
    """A fact extracted from an earlier chapter and valid now."""

    subject: str
    predicate: str
    object: str
    fact_type: str
    confidence: Confidence
    source_chapter: PositiveInt


class ForeshadowingContext(RequestModel):
    """An open setup revealed before the current chapter."""

    foreshadowing_id: EntityId
    description: str
    setup_chapter: PositiveInt
    expected_payoff_chapter: PositiveInt
    importance: str


class ContextBudgetMetadata(RequestModel):
    """Auditable budget and omission information."""

    max_chars: PositiveInt
    estimated_chars: NonNegativeInt
    candidate_items: NonNegativeInt
    included_items: NonNegativeInt
    omitted_items: NonNegativeInt
    omitted_categories: list[str]
    mandatory_outline_exceeded_budget: bool = False


class ChapterContext(RequestModel):
    """Complete writer context assembled from persisted canonical data."""

    project_id: EntityId
    project: ProjectContext
    current_outline: ChapterOutlineContext
    characters: list[CharacterContext] = Field(default_factory=list)
    locations: list[LocationContext] = Field(default_factory=list)
    rules: list[RuleContext] = Field(default_factory=list)
    recent_chapters: list[RecentChapterContext] = Field(default_factory=list)
    known_facts: list[FactContext] = Field(default_factory=list)
    active_foreshadowing: list[ForeshadowingContext] = Field(default_factory=list)
    author_secrets: list[str] = Field(default_factory=list)
    budget: ContextBudgetMetadata
