"""Structured CriticAgent validation and failure tests."""

# ruff: noqa: RUF001 -- Chinese fixture punctuation is intentional.

from copy import deepcopy

import pytest

from storyforge.agents import CriticAgent
from storyforge.demo import build_critic_provider
from storyforge.evaluation.models import ChapterCritique, CriticContext
from storyforge.exceptions import AgentExecutionError, EvaluationError
from storyforge.llm import (
    LLMMessage,
    MockFailure,
    MockLLMProvider,
    PromptReference,
    PromptRequest,
)
from storyforge.prompts import PROMPT_VERSION, build_prompt_registry


def _context(content: str = "林舟沿楼梯进入灯塔，并记录了潮线。") -> CriticContext:
    return CriticContext(
        project_id=1,
        chapter_id=1,
        chapter_number=1,
        genre="mystery",
        premise="A moving lighthouse must be investigated.",
        outline={"key_events": ["enter lighthouse"]},
        content=content,
        summary="林舟进入灯塔。",
        mechanical_summary={"score": 9},
        consistency_summary={"score": 10},
    )


def _valid_payload() -> dict[str, object]:
    provider = build_critic_provider()
    response = provider.generate(
        PromptRequest(
            prompt=PromptReference(name="test", version="v1"),
            messages=(LLMMessage(role="user", content="test"),),
        ),
        ChapterCritique,
    )
    return response.output.model_dump(mode="python")


def test_critic_returns_valid_output_and_prompt_versions_without_database() -> None:
    provider = build_critic_provider()
    result = CriticAgent(provider, build_prompt_registry()).critique(_context())

    assert result.output.pass_recommendation is True
    assert 0 <= result.output.overall_score <= 10
    assert result.provider == "mock"
    assert result.prompt_versions == {
        "critic.system": PROMPT_VERSION,
        "critic.user": PROMPT_VERSION,
    }
    assert provider.call_count == 1
    assert "CriticContext" not in provider.requests[0].messages[-1].content


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (("prose", "score", 11), "valid structured output"),
        (("issues", 0, "severity", "urgent"), "valid structured output"),
        (("overall_score", 0), "valid structured output"),
    ],
)
def test_critic_rejects_invalid_structured_output(
    mutation: tuple[object, ...], expected: str
) -> None:
    payload = deepcopy(_valid_payload())
    if len(mutation) == 2:
        payload[str(mutation[0])] = mutation[1]
    elif isinstance(mutation[1], int):
        items = payload[str(mutation[0])]
        assert isinstance(items, list)
        item = items[mutation[1]]
        assert isinstance(item, dict)
        item[str(mutation[2])] = mutation[3]
    else:
        item = payload[str(mutation[0])]
        assert isinstance(item, dict)
        item[str(mutation[1])] = mutation[2]
    provider = MockLLMProvider({ChapterCritique: payload})

    with pytest.raises(AgentExecutionError, match=expected):
        CriticAgent(provider, build_prompt_registry()).critique(_context())


def test_critical_consistency_issue_cannot_recommend_pass() -> None:
    payload = _valid_payload()
    issues = payload["issues"]
    assert isinstance(issues, list)
    issue = issues[0]
    assert isinstance(issue, dict)
    issue.update({"category": "consistency", "severity": "critical"})
    payload["pass_recommendation"] = True
    provider = MockLLMProvider({ChapterCritique: payload})

    with pytest.raises(AgentExecutionError):
        CriticAgent(provider, build_prompt_registry()).critique(_context())


def test_timeout_schema_failure_empty_content_and_fake_evidence_are_internal_errors() -> None:
    timeout = MockLLMProvider({ChapterCritique: _valid_payload()}, failures=[MockFailure.TIMEOUT])
    with pytest.raises(AgentExecutionError, match="failed to produce valid structured output"):
        CriticAgent(timeout, build_prompt_registry()).critique(_context())

    with pytest.raises(EvaluationError, match="without content"):
        CriticAgent(build_critic_provider(), build_prompt_registry()).critique(_context(" "))

    payload = _valid_payload()
    issues = payload["issues"]
    assert isinstance(issues, list)
    issue = issues[0]
    assert isinstance(issue, dict)
    issue["evidence"] = "This quote does not occur in the chapter."
    with pytest.raises(EvaluationError, match="not present"):
        CriticAgent(MockLLMProvider({ChapterCritique: payload}), build_prompt_registry()).critique(
            _context()
        )


def test_mock_critic_scenarios_are_deterministic_and_cover_required_modes() -> None:
    recommendations = {}
    for scenario in ("normal", "death", "outline", "poor", "conflict"):
        first = CriticAgent(build_critic_provider(scenario), build_prompt_registry()).critique(
            _context()
        )
        second = CriticAgent(build_critic_provider(scenario), build_prompt_registry()).critique(
            _context()
        )
        assert first.output == second.output
        recommendations[scenario] = first.output.pass_recommendation

    assert recommendations == {
        "normal": True,
        "death": False,
        "outline": False,
        "poor": False,
        "conflict": False,
    }


def test_prompt_catalog_registers_critic_templates() -> None:
    registry = build_prompt_registry()
    assert registry.versions("critic.system") == (PROMPT_VERSION,)
    assert registry.versions("critic.user") == (PROMPT_VERSION,)
