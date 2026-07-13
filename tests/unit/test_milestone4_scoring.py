"""Milestone-four combined scoring tests."""

import pytest
from pydantic import ValidationError

from storyforge.demo import build_critic_provider
from storyforge.evaluation import EvaluationScorer
from storyforge.evaluation.config import EvaluationScoringConfig
from storyforge.evaluation.models import ChapterCritique
from storyforge.llm import LLMMessage, PromptReference, PromptRequest


def _critique(scenario: str = "normal") -> ChapterCritique:
    provider = build_critic_provider(scenario)
    return provider.generate(
        PromptRequest(
            prompt=PromptReference(name="test", version="v1"),
            messages=(LLMMessage(role="user", content="test"),),
        ),
        ChapterCritique,
    ).output


def test_normal_weighting_records_raw_and_weighted_scores() -> None:
    result = EvaluationScorer().combine(
        mechanical_score=9,
        critique=_critique(),
        consistency_score=9,
        critical_conflicts=0,
        high_conflicts=0,
        content_empty=False,
    )
    assert result.passed is True
    assert result.recommended_action == "accept"
    assert result.raw_scores["mechanical"] == 9
    assert result.weighted_scores["mechanical"] == pytest.approx(1.8)
    assert 7 <= result.final_score <= 10


def test_invalid_weight_configuration_is_rejected() -> None:
    with pytest.raises(ValidationError, match="sum to 1"):
        EvaluationScoringConfig(
            weights={
                "mechanical": 1,
                "prose": 1,
                "plot": 1,
                "character": 1,
                "pacing": 1,
                "dialogue": 1,
                "emotional_impact": 1,
                "consistency": 1,
                "outline_adherence": 1,
            }
        )


def test_critical_conflict_caps_score_and_blocks_pass() -> None:
    result = EvaluationScorer().combine(
        mechanical_score=10,
        critique=_critique(),
        consistency_score=10,
        critical_conflicts=1,
        high_conflicts=0,
        content_empty=False,
    )
    assert result.final_score <= 5
    assert result.passed is False
    assert "critical_conflict_present" in result.blocking_reasons
    assert result.recommended_action == "human_review"


def test_high_conflict_penalty_and_gate_apply() -> None:
    baseline = EvaluationScorer().combine(
        mechanical_score=10,
        critique=_critique(),
        consistency_score=8,
        critical_conflicts=0,
        high_conflicts=0,
        content_empty=False,
    )
    conflicted = EvaluationScorer().combine(
        mechanical_score=10,
        critique=_critique(),
        consistency_score=8,
        critical_conflicts=0,
        high_conflicts=1,
        content_empty=False,
    )
    assert conflicted.final_score == pytest.approx(baseline.final_score - 0.5)
    assert conflicted.passed is False
    assert "too_many_high_conflicts" in conflicted.blocking_reasons


def test_empty_low_consistency_and_low_outline_each_block() -> None:
    empty = EvaluationScorer().combine(
        mechanical_score=10,
        critique=_critique(),
        consistency_score=10,
        critical_conflicts=0,
        high_conflicts=0,
        content_empty=True,
    )
    assert empty.final_score == 0
    assert empty.recommended_action == "reject"

    low_consistency = EvaluationScorer().combine(
        mechanical_score=10,
        critique=_critique(),
        consistency_score=5,
        critical_conflicts=0,
        high_conflicts=0,
        content_empty=False,
    )
    assert "consistency_score_below_minimum" in low_consistency.blocking_reasons

    low_outline = EvaluationScorer().combine(
        mechanical_score=10,
        critique=_critique("outline"),
        consistency_score=10,
        critical_conflicts=0,
        high_conflicts=0,
        content_empty=False,
    )
    assert "outline_adherence_below_minimum" in low_outline.blocking_reasons
    assert low_outline.recommended_action == "revise"


def test_pass_threshold_is_configurable_and_scores_are_bounded() -> None:
    scorer = EvaluationScorer(EvaluationScoringConfig(pass_threshold=9.9))
    result = scorer.combine(
        mechanical_score=50,
        critique=_critique(),
        consistency_score=-3,
        critical_conflicts=0,
        high_conflicts=0,
        content_empty=False,
    )
    assert 0 <= result.final_score <= 10
    assert result.raw_scores["mechanical"] == 10
    assert result.raw_scores["consistency"] == 0
    assert result.passed is False
