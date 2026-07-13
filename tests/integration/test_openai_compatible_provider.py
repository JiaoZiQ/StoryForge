"""Offline integration tests through the real OpenAI SDK and HTTP mock transport."""

from __future__ import annotations

import json
import logging
from collections import deque
from collections.abc import Callable
from typing import Any, cast
from unittest.mock import patch

import httpx
import openai
import pytest
from pydantic import BaseModel, ConfigDict, SecretStr

from storyforge.llm import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMInvalidResponseError,
    LLMMessage,
    LLMProviderError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMServiceError,
    LLMTimeoutError,
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
    PromptReference,
    PromptRequest,
)

API_KEY = "test-secret-api-key"
BASE_URL = "https://llm.example.test/v1"
MODEL = "structured-test-model"


class StructuredAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    confidence: float


@pytest.fixture
def prompt_request() -> PromptRequest:
    return PromptRequest(
        prompt=PromptReference(name="test.answer", version="2.1.0"),
        messages=(
            LLMMessage(role="system", content="Return a structured answer."),
            LLMMessage(role="user", content="What happens next?"),
        ),
    )


def _config(**overrides: object) -> OpenAICompatibleConfig:
    values: dict[str, object] = {
        "api_key": SecretStr(API_KEY),
        "model": MODEL,
        "base_url": BASE_URL,
        "timeout_seconds": 0.5,
        "max_retries": 2,
        "repair_retries": 1,
        "retry_base_delay_seconds": 0.1,
    }
    values.update(overrides)
    return OpenAICompatibleConfig(**values)  # type: ignore[arg-type]


def _completion(
    request: httpx.Request,
    content: str | None,
    *,
    refusal: str | None = None,
    choices: bool = True,
    finish_reason: str = "stop",
    include_usage: bool = True,
) -> httpx.Response:
    choice_data: list[dict[str, object]] = []
    if choices:
        choice_data.append(
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "refusal": refusal,
                },
                "finish_reason": finish_reason,
                "logprobs": None,
            }
        )
    response_body: dict[str, object] = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1_720_000_000,
        "model": MODEL,
        "choices": choice_data,
    }
    if include_usage:
        response_body["usage"] = {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
        }
    return httpx.Response(200, request=request, json=response_body)


def _error(
    request: httpx.Request, status_code: int, message: str = "provider error"
) -> httpx.Response:
    return httpx.Response(
        status_code,
        request=request,
        json={
            "error": {
                "message": message,
                "type": "provider_error",
                "param": None,
                "code": None,
            }
        },
    )


def _provider(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    config: OpenAICompatibleConfig | None = None,
    delays: list[float] | None = None,
) -> OpenAICompatibleProvider:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    recorded_delays = delays if delays is not None else []
    return OpenAICompatibleProvider(
        config or _config(),
        http_client=http_client,
        sleeper=recorded_delays.append,
    )


def test_success_uses_strict_schema_and_returns_metadata(
    prompt_request: PromptRequest,
) -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == f"{BASE_URL}/chat/completions"
        assert request.headers["authorization"] == f"Bearer {API_KEY}"
        body = json.loads(request.content)
        bodies.append(body)
        return _completion(
            request,
            json.dumps({"answer": "The gate opens.", "confidence": 0.92}),
        )

    with _provider(handler) as provider:
        response = provider.generate(prompt_request, StructuredAnswer)

    assert bodies[0]["model"] == MODEL
    assert bodies[0]["response_format"]["type"] == "json_schema"
    assert bodies[0]["response_format"]["json_schema"]["strict"] is True
    assert response.output == StructuredAnswer(answer="The gate opens.", confidence=0.92)
    assert response.prompt == prompt_request.prompt
    assert response.provider == "openai-compatible"
    assert response.model == MODEL
    assert response.attempts == 1
    assert response.request_id == "chatcmpl-test"
    assert response.usage is not None
    assert response.usage.total_tokens == 18


def test_from_env_reads_key_base_url_and_model(prompt_request: PromptRequest) -> None:
    seen_request = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = True
        assert request.url.host == "configured.example.test"
        assert request.headers["authorization"] == "Bearer configured-secret"
        assert json.loads(request.content)["model"] == "configured-model"
        return _completion(request, '{"answer":"ok","confidence":1.0}')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    environment = {
        "OPENAI_API_KEY": "configured-secret",
        "OPENAI_BASE_URL": "https://configured.example.test/v1",
        "OPENAI_MODEL": "configured-model",
        "LLM_TIMEOUT_SECONDS": "4",
        "LLM_MAX_RETRIES": "0",
        "LLM_REPAIR_RETRIES": "0",
        "LLM_RETRY_BASE_DELAY_SECONDS": "0",
    }
    with OpenAICompatibleProvider.from_env(
        environ=environment,
        http_client=client,
        sleeper=lambda _: None,
    ) as provider:
        assert provider.generate(prompt_request, StructuredAnswer).output.answer == "ok"
    assert seen_request


def test_timeout_uses_exponential_backoff_and_stops(
    prompt_request: PromptRequest,
) -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("simulated timeout", request=request)

    with _provider(handler, delays=delays) as provider:
        with pytest.raises(LLMTimeoutError) as caught:
            provider.generate(prompt_request, StructuredAnswer)

    assert calls == 3
    assert delays == [0.1, 0.2]
    assert caught.value.attempts == 3


def test_retryable_status_recovers(prompt_request: PromptRequest) -> None:
    responses: deque[int] = deque([500, 200])
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = responses.popleft()
        if status == 500:
            return _error(request, status)
        return _completion(request, '{"answer":"recovered","confidence":0.8}')

    with _provider(handler, delays=delays) as provider:
        response = provider.generate(prompt_request, StructuredAnswer)

    assert response.output.answer == "recovered"
    assert response.attempts == 2
    assert delays == [0.1]


def test_rate_limit_retries_are_bounded(prompt_request: PromptRequest) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _error(request, 429)

    with _provider(handler, config=_config(max_retries=1)) as provider:
        with pytest.raises(LLMRateLimitError) as caught:
            provider.generate(prompt_request, StructuredAnswer)

    assert calls == 2
    assert caught.value.status_code == 429
    assert caught.value.attempts == 2


def test_invalid_json_is_repaired_with_a_bounded_retry(
    prompt_request: PromptRequest,
) -> None:
    contents = deque(["not-json", '{"answer":"fixed","confidence":0.7}'])
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return _completion(request, contents.popleft())

    with _provider(handler) as provider:
        response = provider.generate(prompt_request, StructuredAnswer)

    assert response.output.answer == "fixed"
    assert response.attempts == 2
    assert len(bodies[1]["messages"]) == len(bodies[0]["messages"]) + 1
    assert "required JSON schema" in bodies[1]["messages"][-1]["content"]


def test_schema_validation_failure_exhausts_repair_retry(
    prompt_request: PromptRequest,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _completion(request, '{"answer":"missing confidence"}')

    with _provider(handler) as provider:
        with pytest.raises(LLMInvalidResponseError) as caught:
            provider.generate(prompt_request, StructuredAnswer)

    assert calls == 2
    assert caught.value.attempts == 2


def test_connection_failure_retries_are_bounded(prompt_request: PromptRequest) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("simulated connection failure", request=request)

    with _provider(handler, config=_config(max_retries=1)) as provider:
        with pytest.raises(LLMServiceError) as caught:
            provider.generate(prompt_request, StructuredAnswer)

    assert calls == 2
    assert caught.value.attempts == 2


def test_retry_scheduler_failure_is_an_internal_error(
    prompt_request: PromptRequest,
) -> None:
    def fail_to_wait(_: float) -> None:
        raise RuntimeError("simulated scheduler failure")

    client = httpx.Client(transport=httpx.MockTransport(lambda request: _error(request, 500)))
    provider = OpenAICompatibleProvider(
        _config(max_retries=1),
        http_client=client,
        sleeper=fail_to_wait,
    )
    try:
        with pytest.raises(LLMProviderError) as caught:
            provider.generate(prompt_request, StructuredAnswer)
        assert isinstance(caught.value.__cause__, RuntimeError)
    finally:
        provider.close()


def test_missing_key_and_invalid_environment_values_are_internal_errors() -> None:
    with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY"):
        OpenAICompatibleProvider.from_env(
            environ={"OPENAI_MODEL": MODEL},
            sleeper=lambda _: None,
        )
    with pytest.raises(LLMConfigurationError, match="numeric"):
        OpenAICompatibleConfig.from_env(
            {
                "OPENAI_API_KEY": API_KEY,
                "OPENAI_MODEL": MODEL,
                "LLM_MAX_RETRIES": "not-a-number",
            }
        )


def test_sdk_initialization_failure_is_an_internal_error() -> None:
    invalid_client = cast(httpx.Client, object())
    with pytest.raises(LLMConfigurationError) as caught:
        OpenAICompatibleProvider(_config(), http_client=invalid_client)
    assert isinstance(caught.value.__cause__, TypeError)


def test_sdk_close_failure_is_an_internal_error() -> None:
    provider = _provider(lambda request: _completion(request, "{}"))
    with patch.object(provider._client, "close", side_effect=RuntimeError("close failed")):
        with pytest.raises(LLMServiceError) as caught:
            provider.close()
    assert isinstance(caught.value.__cause__, RuntimeError)
    provider.close()


@pytest.mark.parametrize(
    ("external_error", "internal_error"),
    [
        (openai.OpenAIError("simulated SDK failure"), LLMServiceError),
        (RuntimeError("simulated unexpected failure"), LLMProviderError),
    ],
)
def test_unclassified_call_failures_never_cross_provider_boundary(
    prompt_request: PromptRequest,
    external_error: Exception,
    internal_error: type[Exception],
) -> None:
    with _provider(lambda request: _completion(request, "{}")) as provider:
        with patch.object(provider, "_request", side_effect=external_error):
            with pytest.raises(internal_error):
                provider.generate(prompt_request, StructuredAnswer)


def test_logs_never_expose_key_url_credentials_or_provider_body(
    prompt_request: PromptRequest,
    caplog: pytest.LogCaptureFixture,
) -> None:
    leaked_body = "body-secret-that-must-not-be-logged"

    def handler(request: httpx.Request) -> httpx.Response:
        return _error(request, 400, leaked_body)

    config = _config(
        api_key=SecretStr("log-secret-key"),
        max_retries=0,
    )
    caplog.set_level(logging.INFO)
    with _provider(handler, config=config) as provider:
        with pytest.raises(LLMServiceError):
            provider.generate(prompt_request, StructuredAnswer)

    log_text = caplog.text
    assert "log-secret-key" not in log_text
    assert leaked_body not in log_text
    assert "prompt=test.answer" in log_text
    assert "prompt_version=2.1.0" in log_text


def test_authentication_and_refusal_are_mapped_to_internal_errors(
    prompt_request: PromptRequest,
) -> None:
    for status_code in (401, 403):

        def handler(
            request: httpx.Request,
            status: int = status_code,
        ) -> httpx.Response:
            return _error(request, status)

        with _provider(handler) as provider:
            with pytest.raises(LLMAuthenticationError) as auth_error:
                provider.generate(prompt_request, StructuredAnswer)
        assert auth_error.value.status_code == status_code

    with _provider(
        lambda request: _completion(request, None, refusal="I cannot answer."),
    ) as provider:
        with pytest.raises(LLMRefusalError) as refusal_error:
            provider.generate(prompt_request, StructuredAnswer)
    assert refusal_error.value.attempts == 1


def test_empty_choices_become_internal_invalid_response(
    prompt_request: PromptRequest,
) -> None:
    with _provider(
        lambda request: _completion(request, None, choices=False),
        config=_config(repair_retries=0),
    ) as provider:
        with pytest.raises(LLMInvalidResponseError):
            provider.generate(prompt_request, StructuredAnswer)


def test_missing_structured_output_is_repaired(prompt_request: PromptRequest) -> None:
    contents: deque[str | None] = deque([None, '{"answer":"repaired","confidence":0.6}'])

    def handler(request: httpx.Request) -> httpx.Response:
        return _completion(request, contents.popleft(), include_usage=False)

    with _provider(handler) as provider:
        response = provider.generate(prompt_request, StructuredAnswer)

    assert response.output.answer == "repaired"
    assert response.attempts == 2
    assert response.usage is None


@pytest.mark.parametrize(
    ("finish_reason", "error_type"),
    [
        ("length", LLMInvalidResponseError),
        ("content_filter", LLMRefusalError),
    ],
)
def test_non_success_finish_reasons_are_internal_errors(
    prompt_request: PromptRequest,
    finish_reason: str,
    error_type: type[Exception],
) -> None:
    with _provider(
        lambda request: _completion(
            request,
            '{"answer":"partial","confidence":0.1}',
            finish_reason=finish_reason,
        ),
        config=_config(repair_retries=0),
    ) as provider:
        with pytest.raises(error_type):
            provider.generate(prompt_request, StructuredAnswer)


@pytest.mark.parametrize(
    "overrides",
    [
        {"api_key": SecretStr("")},
        {"model": ""},
        {"base_url": ""},
        {"base_url": "http://[::1"},
        {"base_url": "not-a-url"},
        {"base_url": "ftp://llm.example.test/v1"},
        {"base_url": "https://user:password@llm.example.test/v1"},
        {"base_url": "https://llm.example.test/v1?api_key=secret"},
        {"base_url": "https://llm.example.test/v1#secret"},
        {"timeout_seconds": 0},
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": float("inf")},
        {"max_retries": -1},
        {"repair_retries": -1},
        {"retry_base_delay_seconds": -1},
        {"retry_base_delay_seconds": float("nan")},
        {"retry_base_delay_seconds": float("inf")},
    ],
)
def test_invalid_provider_config_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(LLMConfigurationError):
        _config(**overrides)
