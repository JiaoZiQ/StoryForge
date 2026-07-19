"""Deterministic, offline LLM provider for development and tests."""

from collections import deque
from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from enum import StrEnum

from pydantic import BaseModel, ValidationError

from storyforge.enums import TokenUsageSource
from storyforge.llm.exceptions import (
    LLMConfigurationError,
    LLMContextLengthError,
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMServiceError,
    LLMTimeoutError,
)
from storyforge.llm.types import LLMResponse, PromptRequest, ResponseT, TokenUsage

type MockPayload = BaseModel | Mapping[str, object]
type MockResponseSelector = Callable[[PromptRequest], MockPayload]


class MockFailure(StrEnum):
    """Failure injected into one deterministic mock call."""

    TIMEOUT = "timeout"
    INVALID_JSON = "invalid_json"
    SCHEMA_VALIDATION = "schema_validation"
    CALL_FAILURE = "call_failure"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    CONTEXT_LENGTH = "context_length"
    CONTENT_POLICY = "content_policy"


class MockLLMProvider:
    """Return registered Pydantic payloads without accessing the network."""

    provider_name = "mock"

    def __init__(
        self,
        responses: Mapping[type[BaseModel], MockPayload] | None = None,
        *,
        failures: Iterable[MockFailure] = (),
        model: str = "storyforge-deterministic-mock",
    ) -> None:
        self._responses: dict[type[BaseModel], deque[dict[str, object]]] = {}
        self._selectors: dict[type[BaseModel], MockResponseSelector] = {}
        for response_model, payload in (responses or {}).items():
            self.register_response(response_model, payload)
        self._failures = deque(failures)
        self._model = model
        self.call_count = 0
        self.requests: list[PromptRequest] = []

    def register_response(
        self,
        response_model: type[BaseModel],
        payload: MockPayload,
    ) -> None:
        """Register or replace deterministic data for one response model."""
        if isinstance(payload, BaseModel):
            data = payload.model_dump(mode="python")
        else:
            data = dict(payload)
        self._responses[response_model] = deque([deepcopy(data)])

    def register_responses(
        self,
        response_model: type[BaseModel],
        payloads: Iterable[MockPayload],
    ) -> None:
        """Register a deterministic sequence, reusing its final item thereafter."""
        items: deque[dict[str, object]] = deque()
        for payload in payloads:
            data = (
                payload.model_dump(mode="python")
                if isinstance(payload, BaseModel)
                else dict(payload)
            )
            items.append(deepcopy(data))
        if not items:
            raise ValueError("At least one mock response is required")
        self._responses[response_model] = items

    def queue_failures(self, failures: Iterable[MockFailure]) -> None:
        """Append deterministic failures for subsequent calls in test/demo order."""
        self._failures.extend(failures)

    def register_response_selector(
        self,
        response_model: type[BaseModel],
        selector: MockResponseSelector,
    ) -> None:
        """Select deterministic data from request content without process-local ordering."""
        self._selectors[response_model] = selector

    def generate(
        self,
        request: PromptRequest,
        response_model: type[ResponseT],
    ) -> LLMResponse[ResponseT]:
        """Validate and return the configured response for ``response_model``."""
        self.call_count += 1
        self.requests.append(request)
        failure = self._failures.popleft() if self._failures else None
        if failure is MockFailure.TIMEOUT:
            raise LLMTimeoutError("Mock LLM request timed out", attempts=1)
        if failure is MockFailure.INVALID_JSON:
            raise LLMInvalidResponseError("Mock LLM returned invalid JSON", attempts=1)
        if failure is MockFailure.SCHEMA_VALIDATION:
            raise LLMInvalidResponseError(
                "Mock LLM response failed schema validation",
                attempts=1,
            )
        if failure is MockFailure.CALL_FAILURE:
            raise LLMServiceError("Mock LLM call failed", attempts=1)
        if failure is MockFailure.RATE_LIMIT:
            raise LLMRateLimitError("Mock LLM rate limited", attempts=1, status_code=429)
        if failure is MockFailure.SERVER_ERROR:
            raise LLMServiceError("Mock LLM service error", attempts=1, status_code=503)
        if failure is MockFailure.CONTEXT_LENGTH:
            raise LLMContextLengthError("Mock LLM context length exceeded", attempts=1)
        if failure is MockFailure.CONTENT_POLICY:
            raise LLMRefusalError("Mock LLM content policy rejection", attempts=1)

        selector = self._selectors.get(response_model)
        configured = self._responses.get(response_model)
        if selector is None and not configured:
            raise LLMConfigurationError(
                f"No deterministic response registered for {response_model.__name__}"
            )
        try:
            if selector is not None:
                selected = selector(request)
                payload = (
                    selected.model_dump(mode="python")
                    if isinstance(selected, BaseModel)
                    else dict(selected)
                )
            else:
                assert configured is not None
                payload = configured.popleft() if len(configured) > 1 else configured[0]
            output = response_model.model_validate(deepcopy(payload))
        except ValidationError as exc:
            raise LLMInvalidResponseError(
                "Mock LLM response failed schema validation",
                attempts=1,
            ) from exc
        return LLMResponse(
            output=output,
            provider=self.provider_name,
            model=self._model,
            prompt=request.prompt,
            attempts=1,
            usage=self._usage(request, output),
        )

    @staticmethod
    def _usage(request: PromptRequest, output: BaseModel) -> TokenUsage:
        input_chars = sum(len(message.content) for message in request.messages)
        output_chars = len(output.model_dump_json())
        input_tokens = max(1, (input_chars + 3) // 4)
        output_tokens = max(1, (output_chars + 3) // 4)
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            source=TokenUsageSource.MOCK,
        )
