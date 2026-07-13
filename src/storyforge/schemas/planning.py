"""Validated inputs and structured outputs for milestone-three planning."""

from typing import Self

from pydantic import Field, model_validator

from storyforge.schemas.base import (
    CategoryText,
    EntityId,
    LongText,
    PositiveInt,
    RequestModel,
    ShortText,
)


class PlanningRequest(RequestModel):
    """Minimal project data allowed to cross into the planner prompt."""

    project_id: EntityId
    title: ShortText
    genre: CategoryText
    premise: LongText
    target_chapters: PositiveInt
    target_words_per_chapter: PositiveInt
    language: str = Field(min_length=2, max_length=32)
    tone: str | None = Field(default=None, min_length=1, max_length=100)
    audience: str | None = Field(default=None, min_length=1, max_length=100)


class CharacterPlan(RequestModel):
    """A character profile produced by the planner."""

    name: ShortText
    role: CategoryText
    description: LongText
    goals: list[ShortText] = Field(min_length=1)
    personality: list[ShortText] = Field(min_length=1)
    speech_style: LongText
    initial_state: LongText
    secrets: list[LongText] = Field(default_factory=list)


class LocationPlan(RequestModel):
    """A location and the local rules that apply there."""

    name: ShortText
    description: LongText
    rules: list[LongText] = Field(default_factory=list)


class StoryRulePlan(RequestModel):
    """One explicit world or narrative rule."""

    category: CategoryText
    statement: LongText


class ChapterPlan(RequestModel):
    """Structured plan for one chapter."""

    chapter_number: PositiveInt
    title: ShortText
    objective: LongText
    summary: LongText
    key_events: list[LongText] = Field(min_length=1)
    participating_characters: list[ShortText] = Field(min_length=1)
    locations: list[ShortText] = Field(min_length=1)
    required_facts: list[LongText] = Field(default_factory=list)
    forbidden_reveals: list[LongText] = Field(default_factory=list)
    setup_foreshadowing: list[LongText] = Field(default_factory=list)
    payoff_foreshadowing: list[LongText] = Field(default_factory=list)
    ending_hook: LongText


class ForeshadowingPlan(RequestModel):
    """A planned setup/payoff pair validated against chapter bounds."""

    description: LongText
    setup_chapter: PositiveInt
    expected_payoff_chapter: PositiveInt
    importance: str = Field(default="medium", pattern="^(low|medium|high)$")

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        """Reject payoff chapters that precede their setup."""
        if self.expected_payoff_chapter < self.setup_chapter:
            raise ValueError("expected payoff chapter must not precede setup chapter")
        return self


class NovelPlan(RequestModel):
    """Complete, mechanically validated output of the planner agent."""

    logline: LongText
    themes: list[ShortText] = Field(min_length=1)
    world_summary: LongText
    central_conflict: LongText
    ending_direction: LongText
    style_guide: LongText
    characters: list[CharacterPlan] = Field(min_length=1)
    locations: list[LocationPlan] = Field(min_length=1)
    story_rules: list[StoryRulePlan] = Field(min_length=1)
    chapter_plans: list[ChapterPlan] = Field(min_length=1)
    foreshadowing: list[ForeshadowingPlan] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_internal_references(self) -> Self:
        """Reject duplicates, gaps, and unknown chapter references."""
        character_names = [item.name for item in self.characters]
        location_names = [item.name for item in self.locations]
        if len(set(character_names)) != len(character_names):
            raise ValueError("character names must be unique")
        if len(set(location_names)) != len(location_names):
            raise ValueError("location names must be unique")

        numbers = [item.chapter_number for item in self.chapter_plans]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError("chapter numbers must be consecutive and start at one")
        known_characters = set(character_names)
        known_locations = set(location_names)
        for chapter in self.chapter_plans:
            unknown_characters = set(chapter.participating_characters) - known_characters
            unknown_locations = set(chapter.locations) - known_locations
            if unknown_characters:
                raise ValueError(f"unknown chapter characters: {sorted(unknown_characters)}")
            if unknown_locations:
                raise ValueError(f"unknown chapter locations: {sorted(unknown_locations)}")
        for item in self.foreshadowing:
            if item.expected_payoff_chapter > len(self.chapter_plans):
                raise ValueError("foreshadowing payoff exceeds planned chapter count")
        return self


def validate_plan_for_request(plan: NovelPlan, request: PlanningRequest) -> None:
    """Validate plan invariants that depend on the persisted project request."""
    if len(plan.chapter_plans) != request.target_chapters:
        raise ValueError("planned chapter count does not match project target")
    for item in plan.foreshadowing:
        if item.setup_chapter > request.target_chapters:
            raise ValueError("foreshadowing setup exceeds project chapter count")
