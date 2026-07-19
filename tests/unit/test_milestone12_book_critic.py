"""Whole-book critic agent contract and deterministic Mock coverage."""

import pytest
from pydantic import ValidationError

from storyforge.agents import BookCriticAgent
from storyforge.book.mock import build_mock_book_critique
from storyforge.book.models import BookCriticContext, BookIssue
from storyforge.exceptions import EvaluationError
from storyforge.llm import MockLLMProvider
from storyforge.prompts import build_prompt_registry


def _context() -> BookCriticContext:
    return BookCriticContext(
        project_title="Tide Archive",
        premise="An archivist repairs a broken timeline.",
        book_summary="Five compressed chapter summaries.",
        chapter_summaries=[{"chapter": 1, "summary": "The clue appears", "score": 8.0}],
        timeline_summary={"events": 3, "conflicts": 0},
        character_arc_summary={"points": 5, "issues": 0},
        relationship_summary=[],
        foreshadowing_summary={"payoff_rate": 1.0},
        pacing_summary={"score": 8.0},
        transition_summary={"average": 8.0},
        repetition_summary={"candidates": 0},
        chapter_score_trend=[8.0],
    )


def test_book_critic_returns_structured_versioned_mock_output() -> None:
    provider = MockLLMProvider()
    provider.register_response(type(build_mock_book_critique()), build_mock_book_critique())
    result = BookCriticAgent(provider, build_prompt_registry()).critique(_context())

    assert result.output.pass_recommendation
    assert result.prompt_versions == {
        "book_critic.system": "v1",
        "book_critic.user": "v1",
    }
    assert provider.call_count == 1


def test_book_critic_rejects_empty_chapter_summary_context() -> None:
    provider = MockLLMProvider()
    provider.register_response(type(build_mock_book_critique()), build_mock_book_critique())
    context = _context().model_copy(update={"chapter_summaries": []})

    with pytest.raises(EvaluationError, match="without chapter summaries"):
        BookCriticAgent(provider, build_prompt_registry()).critique(context)


def test_critical_book_issue_cannot_recommend_pass() -> None:
    issue = BookIssue(
        code="timeline.critical",
        category="timeline",
        severity="critical",
        description="Contradiction",
        chapter_numbers=[1, 2],
        suggestion="Revise",
    )
    with pytest.raises(ValidationError, match="critical global issue"):
        build_mock_book_critique().model_copy(
            update={"global_issues": [issue], "pass_recommendation": True}
        ).model_validate(
            {
                **build_mock_book_critique().model_dump(),
                "global_issues": [issue.model_dump()],
                "pass_recommendation": True,
            }
        )
