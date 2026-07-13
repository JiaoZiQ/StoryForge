"""Tests for the deterministic offline LLM provider."""

from collections.abc import Callable

import pytest
from pydantic import BaseModel, ConfigDict

from storyforge.llm import (
    LLMConfigurationError,
    LLMInvalidResponseError,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMServiceError,
    LLMTimeoutError,
    MockFailure,
    MockLLMProvider,
    PromptReference,
    PromptRequest,
)


class PlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    beats: list[str]


class ScoreOutput(BaseModel):
    score: int


@pytest.fixture
def prompt_request() -> PromptRequest:
    return PromptRequest(
        prompt=PromptReference(name="chapter.plan", version="1.0.0"),
        messages=(LLMMessage(role="user", content="Plan the next chapter."),),
    )


def test_mock_returns_deterministic_data_for_multiple_models(
    prompt_request: PromptRequest,
) -> None:
    provider: LLMProvider = MockLLMProvider(
        {
            PlanOutput: {"title": "Arrival", "beats": ["dock", "warning"]},
            ScoreOutput: ScoreOutput(score=91),
        }
    )

    first = provider.generate(prompt_request, PlanOutput)
    second = provider.generate(prompt_request, PlanOutput)
    score = provider.generate(prompt_request, ScoreOutput)

    assert (
        first.output
        == second.output
        == PlanOutput(
            title="Arrival",
            beats=["dock", "warning"],
        )
    )
    assert first.output is not second.output
    assert first.provider == "mock"
    assert first.prompt.version == "1.0.0"
    assert first.attempts == 1
    assert score.output.score == 91


def test_mock_response_can_be_replaced(prompt_request: PromptRequest) -> None:
    provider = MockLLMProvider()
    provider.register_response(ScoreOutput, {"score": 40})
    provider.register_response(ScoreOutput, {"score": 88})

    response = provider.generate(prompt_request, ScoreOutput)
    assert response.output.score == 88
    assert provider.call_count == 1


def test_mock_snapshots_mutable_registered_data(prompt_request: PromptRequest) -> None:
    beats = ["dock"]
    payload: dict[str, object] = {"title": "Arrival", "beats": beats}
    provider = MockLLMProvider({PlanOutput: payload})

    payload["title"] = "Changed"
    beats.append("mutation")

    response = provider.generate(prompt_request, PlanOutput)
    assert response.output == PlanOutput(title="Arrival", beats=["dock"])


@pytest.mark.parametrize(
    ("failure", "error_type"),
    [
        (MockFailure.TIMEOUT, LLMTimeoutError),
        (MockFailure.INVALID_JSON, LLMInvalidResponseError),
        (MockFailure.SCHEMA_VALIDATION, LLMInvalidResponseError),
        (MockFailure.CALL_FAILURE, LLMServiceError),
    ],
)
def test_mock_can_simulate_each_failure_mode(
    prompt_request: PromptRequest,
    failure: MockFailure,
    error_type: type[Exception],
) -> None:
    provider = MockLLMProvider(
        {ScoreOutput: {"score": 80}},
        failures=[failure],
    )

    with pytest.raises(error_type):
        provider.generate(prompt_request, ScoreOutput)
    assert provider.call_count == 1


def test_mock_failure_sequence_is_deterministic(prompt_request: PromptRequest) -> None:
    provider = MockLLMProvider(
        {ScoreOutput: {"score": 80}},
        failures=[MockFailure.TIMEOUT],
    )

    with pytest.raises(LLMTimeoutError):
        provider.generate(prompt_request, ScoreOutput)
    assert provider.generate(prompt_request, ScoreOutput).output.score == 80
    assert provider.call_count == 2


def test_mock_rejects_missing_or_invalid_registered_data(
    prompt_request: PromptRequest,
) -> None:
    provider = MockLLMProvider({ScoreOutput: {"score": "not-an-integer"}})
    with pytest.raises(LLMInvalidResponseError) as invalid:
        provider.generate(prompt_request, ScoreOutput)
    assert invalid.value.attempts == 1

    with pytest.raises(LLMConfigurationError, match="No deterministic response"):
        MockLLMProvider().generate(prompt_request, ScoreOutput)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: LLMMessage(role="user", content=" "),
        lambda: PromptReference(name="", version="1"),
        lambda: PromptReference(name="name", version=""),
        lambda: PromptRequest(prompt=PromptReference("name", "1"), messages=()),
    ],
)
def test_llm_boundary_values_reject_empty_content(factory: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        factory()


def test_llm_response_rejects_non_positive_attempts(prompt_request: PromptRequest) -> None:
    with pytest.raises(ValueError, match="attempts"):
        LLMResponse(
            output=ScoreOutput(score=80),
            provider="mock",
            model="mock",
            prompt=prompt_request.prompt,
            attempts=0,
        )
