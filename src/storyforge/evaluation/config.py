"""Central, validated rule thresholds and score weights."""

from math import isclose
from typing import Self

from pydantic import Field, model_validator

from storyforge.schemas.base import RequestModel


def _mechanical_penalties() -> dict[str, float]:
    return {
        "empty_content": 10.0,
        "length_too_short": 2.0,
        "length_too_long": 1.5,
        "duplicate_paragraph": 1.5,
        "repeated_ngram_high": 1.5,
        "uniform_sentence_lengths": 0.8,
        "similar_paragraph_openings": 0.8,
        "ai_cliche": 0.8,
        "banned_phrase": 1.0,
        "punctuation_overuse": 0.8,
        "dialogue_ratio_high": 0.8,
        "dialogue_ratio_low": 0.5,
        "long_paragraph": 0.8,
        "short_paragraphs": 0.8,
        "punctuation_anomaly": 0.8,
        "embedded_heading_or_summary": 1.0,
    }


class MechanicalEvaluationConfig(RequestModel):
    """All tunable thresholds for deterministic mechanical rules."""

    version: str = "m4-mechanical-v1"
    min_length_ratio: float = Field(default=0.6, gt=0)
    max_length_ratio: float = Field(default=1.6, gt=1)
    ngram_size: int = Field(default=4, ge=2, le=10)
    repeated_ngram_ratio_threshold: float = Field(default=0.18, ge=0, le=1)
    sentence_stddev_min: float = Field(default=2.5, ge=0)
    sentence_uniformity_min_count: int = Field(default=4, ge=2)
    similar_opening_length: int = Field(default=6, ge=2)
    similar_opening_run: int = Field(default=3, ge=2)
    punctuation_per_100_limit: float = Field(default=8, ge=0)
    dialogue_ratio_min: float = Field(default=0.04, ge=0, le=1)
    dialogue_ratio_max: float = Field(default=0.7, ge=0, le=1)
    dialogue_check_min_chars: int = Field(default=100, ge=0)
    short_paragraph_chars: int = Field(default=30, ge=1)
    long_paragraph_chars: int = Field(default=500, ge=1)
    short_paragraph_ratio_limit: float = Field(default=0.65, ge=0, le=1)
    long_paragraph_ratio_limit: float = Field(default=0.25, ge=0, le=1)
    punctuation_ratio_limit: float = Field(default=0.14, ge=0, le=1)
    ai_phrases: tuple[str, ...] = (
        "值得注意的是",
        "不禁让人",
        "仿佛在诉说",
        "空气中弥漫着",
        "it is worth noting",
        "a testament to",
    )
    banned_phrases: tuple[str, ...] = ("违禁表达", "[禁止词]")
    penalties: dict[str, float] = Field(default_factory=_mechanical_penalties)

    @model_validator(mode="after")
    def validate_thresholds(self) -> Self:
        """Keep paired thresholds and penalties internally consistent."""
        if self.dialogue_ratio_min >= self.dialogue_ratio_max:
            raise ValueError("dialogue ratio minimum must be below maximum")
        if self.short_paragraph_chars >= self.long_paragraph_chars:
            raise ValueError("short paragraph threshold must be below long threshold")
        required = set(_mechanical_penalties())
        if required - self.penalties.keys():
            raise ValueError("mechanical penalty configuration is incomplete")
        if any(value < 0 for value in self.penalties.values()):
            raise ValueError("mechanical penalties must be non-negative")
        return self


def _default_weights() -> dict[str, float]:
    return {
        "mechanical": 0.20,
        "prose": 0.15,
        "plot": 0.15,
        "character": 0.10,
        "pacing": 0.10,
        "dialogue": 0.05,
        "emotional_impact": 0.05,
        "consistency": 0.15,
        "outline_adherence": 0.05,
    }


class EvaluationScoringConfig(RequestModel):
    """Validated score weights and hard pass gates."""

    version: str = "m4-scoring-v1"
    weights: dict[str, float] = Field(default_factory=_default_weights)
    pass_threshold: float = Field(default=7.0, ge=0, le=10)
    critical_score_cap: float = Field(default=5.0, ge=0, le=10)
    high_conflict_penalty: float = Field(default=0.5, ge=0, le=10)
    max_high_conflicts: int = Field(default=0, ge=0)
    min_consistency_score: float = Field(default=6.5, ge=0, le=10)
    min_outline_adherence_score: float = Field(default=6.0, ge=0, le=10)

    @model_validator(mode="after")
    def validate_weights(self) -> Self:
        """Require the exact supported dimensions and a unit weight sum."""
        expected = set(_default_weights())
        if set(self.weights) != expected:
            raise ValueError("scoring weights must contain exactly the supported dimensions")
        if any(value < 0 for value in self.weights.values()):
            raise ValueError("scoring weights must be non-negative")
        if not isclose(sum(self.weights.values()), 1.0, abs_tol=1e-9):
            raise ValueError("scoring weights must sum to 1")
        return self
