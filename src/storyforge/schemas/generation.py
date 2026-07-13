"""Structured chapter drafting, extraction, and service result schemas."""

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from storyforge.schemas.base import (
    Confidence,
    EntityId,
    LongText,
    NonNegativeInt,
    PositiveInt,
    RequestModel,
    ShortText,
)


class NewEntity(RequestModel):
    """An entity mentioned by a draft but not yet promoted to canonical data."""

    entity_type: str = Field(pattern="^(character|location|object|organization)$")
    name: ShortText
    description: LongText


class StyleSelfCheck(RequestModel):
    """Writer-provided mechanical self-check, not an M4 evaluation."""

    follows_outline: bool
    avoids_forbidden_reveals: bool
    notes: list[LongText] = Field(default_factory=list)


class ChapterDraft(RequestModel):
    """Validated structured output returned by WriterAgent."""

    title: ShortText
    content: LongText
    summary: LongText
    new_entities: list[NewEntity] = Field(default_factory=list)
    style_self_check: StyleSelfCheck


class ExtractedFact(RequestModel):
    """One canonical fact extracted from generated prose."""

    subject: ShortText
    predicate: ShortText
    object: LongText
    fact_type: str = Field(min_length=1, max_length=50)
    confidence: Confidence
    source_quote: LongText
    valid_from_chapter: PositiveInt
    valid_to_chapter: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """Reject inverted chapter validity ranges."""
        if self.valid_to_chapter is not None and self.valid_to_chapter < self.valid_from_chapter:
            raise ValueError("fact validity range is inverted")
        return self


class CharacterStateUpdate(RequestModel):
    """A high-confidence canonical character state change."""

    character_name: ShortText
    field: str = Field(pattern="^current_state$")
    value: LongText
    confidence: Confidence
    source_quote: LongText


class ForeshadowingUpdate(RequestModel):
    """A setup, advancement, or resolution inferred from the current prose."""

    action: Literal["setup", "advance", "resolve"]
    description: LongText
    foreshadowing_id: EntityId | None = None
    confidence: Confidence
    source_quote: LongText


class FactExtractionResult(RequestModel):
    """Validated aggregate output returned by FactExtractorAgent."""

    facts: list[ExtractedFact] = Field(default_factory=list)
    character_updates: list[CharacterStateUpdate] = Field(default_factory=list)
    foreshadowing_updates: list[ForeshadowingUpdate] = Field(default_factory=list)


class FactExtractionRequest(RequestModel):
    """Minimal generated material allowed into the extraction prompt."""

    project_id: EntityId
    chapter_number: PositiveInt
    chapter_content: LongText
    context_summary: LongText
    new_entities: list[NewEntity] = Field(default_factory=list)
    confidence_threshold: Confidence = 0.7


class ChapterGenerationRequest(RequestModel):
    """Input for the chapter generation application service."""

    project_id: EntityId
    chapter_number: PositiveInt
    regenerate: bool = False
    max_context_chars: PositiveInt = 24_000


class GenerationMetadata(RequestModel):
    """Reproducibility and timing metadata persisted with a chapter."""

    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    prompt_versions: dict[str, str]
    attempts: PositiveInt
    duration_ms: NonNegativeInt
    generated_at: datetime


class ChapterGenerationResult(RequestModel):
    """Stable result returned after draft and facts are durably persisted."""

    project_id: EntityId
    chapter_id: EntityId
    chapter_number: PositiveInt
    version: PositiveInt
    status: str
    title: ShortText
    summary: LongText
    content: LongText
    fact_count: NonNegativeInt
    character_update_count: NonNegativeInt
    foreshadowing_update_count: NonNegativeInt
    generation_metadata: GenerationMetadata
