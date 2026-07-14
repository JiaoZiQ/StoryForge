"""OpenAI-compatible structured-output provider with project-owned reliability policy."""

from __future__ import annotations

import json
import logging
import math
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import cast

import httpx
import openai
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import SecretStr, ValidationError

from storyforge.llm.exceptions import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMInvalidResponseError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMServiceError,
    LLMTimeoutError,
)
from storyforge.llm.types import LLMResponse, PromptRequest, ResponseT, TokenUsage

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
STRUCTURED_OUTPUT_REPAIR_INSTRUCTION = (
    "The previous response did not match the required JSON schema. "
    "Return only a valid response that strictly matches that schema."
)
RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429})


@dataclass(frozen=True, slots=True)
class OpenAICompatibleConfig:
    """Validated configuration for one OpenAI-compatible endpoint."""

    api_key: SecretStr
    model: str
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 30.0
    max_retries: int = 2
    repair_retries: int = 1
    retry_base_delay_seconds: float = 0.5

    def __post_init__(self) -> None:
        if not self.api_key.get_secret_value():
            raise LLMConfigurationError("OPENAI_API_KEY is required")
        if not self.model.strip():
            raise LLMConfigurationError("OPENAI_MODEL is required")
        if not self.base_url.strip():
            raise LLMConfigurationError("OPENAI_BASE_URL must not be empty")
        try:
            endpoint = httpx.URL(self.base_url)
        except httpx.InvalidURL as exc:
            raise LLMConfigurationError("OPENAI_BASE_URL is invalid") from exc
        if endpoint.scheme not in {"http", "https"} or not endpoint.host:
            raise LLMConfigurationError("OPENAI_BASE_URL must be an HTTP(S) URL")
        if endpoint.userinfo:
            raise LLMConfigurationError("OPENAI_BASE_URL must not contain credentials")
        if endpoint.query or endpoint.fragment:
            raise LLMConfigurationError("OPENAI_BASE_URL must not contain query or fragment data")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise LLMConfigurationError("LLM_TIMEOUT_SECONDS must be positive")
        if self.max_retries < 0 or self.repair_retries < 0:
            raise LLMConfigurationError("LLM retry counts must not be negative")
        if not math.isfinite(self.retry_base_delay_seconds) or self.retry_base_delay_seconds < 0:
            raise LLMConfigurationError("LLM_RETRY_BASE_DELAY_SECONDS must not be negative")

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> OpenAICompatibleConfig:
        """Load provider settings from environment variables at call time."""
        values = os.environ if environ is None else environ
        api_key = values.get("OPENAI_API_KEY", "")
        model = values.get("OPENAI_MODEL", "")
        base_url = values.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
        try:
            timeout_seconds = float(values.get("LLM_TIMEOUT_SECONDS", "30"))
            max_retries = int(values.get("LLM_MAX_RETRIES", "2"))
            repair_retries = int(values.get("LLM_REPAIR_RETRIES", "1"))
            retry_base_delay_seconds = float(values.get("LLM_RETRY_BASE_DELAY_SECONDS", "0.5"))
        except ValueError as exc:
            raise LLMConfigurationError("LLM numeric environment settings are invalid") from exc
        return cls(
            api_key=SecretStr(api_key),
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            repair_retries=repair_retries,
            retry_base_delay_seconds=retry_base_delay_seconds,
        )


class OpenAICompatibleProvider:
    """Call an OpenAI-compatible endpoint and return validated Pydantic output."""

    provider_name = "openai-compatible"

    def __init__(
        self,
        config: OpenAICompatibleConfig,
        *,
        http_client: httpx.Client | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self._config = config
        self._sleeper = sleeper or time.sleep
        try:
            self._client = OpenAI(
                api_key=config.api_key.get_secret_value(),
                base_url=config.base_url,
                timeout=config.timeout_seconds,
                max_retries=0,
                http_client=http_client,
            )
        except Exception as exc:
            raise LLMConfigurationError("Could not initialize the LLM provider") from exc

    @classmethod
    def from_env(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        http_client: httpx.Client | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> OpenAICompatibleProvider:
        """Construct a provider from environment variables."""
        return cls(
            OpenAICompatibleConfig.from_env(environ),
            http_client=http_client,
            sleeper=sleeper,
        )

    def close(self) -> None:
        """Close the underlying SDK client and its HTTP resources."""
        try:
            self._client.close()
        except Exception as exc:
            raise LLMServiceError("Could not close the LLM provider", attempts=1) from exc

    def __enter__(self) -> OpenAICompatibleProvider:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()

    def generate(
        self,
        request: PromptRequest,
        response_model: type[ResponseT],
    ) -> LLMResponse[ResponseT]:
        """Call the endpoint with bounded transport and response-repair retries."""
        messages = self._to_sdk_messages(request)
        attempts = 0
        transport_retries = 0
        repair_retries = 0

        while True:
            attempts += 1
            logger.info(
                "Calling LLM provider=%s model=%s prompt=%s prompt_version=%s attempt=%d",
                self.provider_name,
                self._config.model,
                request.prompt.name,
                request.prompt.version,
                attempts,
            )
            try:
                return self._request(messages, request, response_model, attempts)
            except LLMRefusalError:
                raise
            except LLMInvalidResponseError as exc:
                if repair_retries >= self._config.repair_retries:
                    raise LLMInvalidResponseError(
                        "LLM response did not match the required schema",
                        attempts=attempts,
                    ) from exc
                repair_retries += 1
                messages = [
                    *messages,
                    cast(
                        ChatCompletionMessageParam,
                        {"role": "system", "content": STRUCTURED_OUTPUT_REPAIR_INSTRUCTION},
                    ),
                ]
                logger.warning(
                    "Retrying LLM structured output provider=%s model=%s attempt=%d",
                    self.provider_name,
                    self._config.model,
                    attempts,
                )
            except openai.ContentFilterFinishReasonError as exc:
                raise LLMRefusalError(
                    "LLM provider filtered the response",
                    attempts=attempts,
                ) from exc
            except openai.APITimeoutError as exc:
                if transport_retries >= self._config.max_retries:
                    raise LLMTimeoutError("LLM request timed out", attempts=attempts) from exc
                self._backoff(transport_retries, attempts, "timeout")
                transport_retries += 1
            except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
                raise LLMAuthenticationError(
                    "LLM provider rejected the configured credentials",
                    attempts=attempts,
                    status_code=exc.status_code,
                ) from exc
            except openai.RateLimitError as exc:
                if transport_retries >= self._config.max_retries:
                    raise LLMRateLimitError(
                        "LLM provider rate limit retries exhausted",
                        attempts=attempts,
                        status_code=exc.status_code,
                    ) from exc
                self._backoff(transport_retries, attempts, "rate_limit")
                transport_retries += 1
            except openai.APIStatusError as exc:
                if self._is_retryable_status(exc.status_code) and (
                    transport_retries < self._config.max_retries
                ):
                    self._backoff(transport_retries, attempts, "status")
                    transport_retries += 1
                    continue
                raise LLMServiceError(
                    "LLM provider returned a non-success status",
                    attempts=attempts,
                    status_code=exc.status_code,
                ) from exc
            except openai.APIConnectionError as exc:
                if transport_retries >= self._config.max_retries:
                    raise LLMServiceError(
                        "LLM provider connection retries exhausted",
                        attempts=attempts,
                    ) from exc
                self._backoff(transport_retries, attempts, "connection")
                transport_retries += 1
            except (json.JSONDecodeError, ValidationError, openai.LengthFinishReasonError) as exc:
                invalid = LLMInvalidResponseError(
                    "LLM response did not match the required schema",
                    attempts=attempts,
                )
                if repair_retries >= self._config.repair_retries:
                    raise invalid from exc
                repair_retries += 1
                messages = [
                    *messages,
                    cast(
                        ChatCompletionMessageParam,
                        {"role": "system", "content": STRUCTURED_OUTPUT_REPAIR_INSTRUCTION},
                    ),
                ]
                logger.warning(
                    "Retrying LLM structured output provider=%s model=%s attempt=%d",
                    self.provider_name,
                    self._config.model,
                    attempts,
                )
            except openai.OpenAIError as exc:
                raise LLMServiceError("LLM provider call failed", attempts=attempts) from exc
            except Exception as exc:
                raise LLMProviderError(
                    "Unexpected LLM provider failure", attempts=attempts
                ) from exc

    def _request(
        self,
        messages: list[ChatCompletionMessageParam],
        request: PromptRequest,
        response_model: type[ResponseT],
        attempts: int,
    ) -> LLMResponse[ResponseT]:
        completion = self._client.chat.completions.parse(
            model=self._config.model,
            messages=messages,
            response_format=response_model,
        )
        if not completion.choices:
            raise LLMInvalidResponseError("LLM response contained no choices", attempts=attempts)
        message = completion.choices[0].message
        if message.refusal:
            raise LLMRefusalError("LLM provider refused the request", attempts=attempts)
        if message.parsed is None:
            raise LLMInvalidResponseError(
                "LLM response contained no structured output",
                attempts=attempts,
            )
        output = response_model.model_validate(message.parsed)

        usage = None
        if completion.usage is not None:
            usage = TokenUsage(
                input_tokens=completion.usage.prompt_tokens,
                output_tokens=completion.usage.completion_tokens,
                total_tokens=completion.usage.total_tokens,
            )
        return LLMResponse(
            output=output,
            provider=self.provider_name,
            model=completion.model,
            prompt=request.prompt,
            attempts=attempts,
            usage=usage,
            request_id=completion.id,
        )

    def _backoff(self, retry_index: int, attempt: int, reason: str) -> None:
        delay = self._config.retry_base_delay_seconds * (2**retry_index)
        logger.warning(
            "Retrying LLM provider=%s model=%s reason=%s attempt=%d delay_seconds=%.3f",
            self.provider_name,
            self._config.model,
            reason,
            attempt,
            delay,
        )
        try:
            self._sleeper(delay)
        except Exception as exc:
            raise LLMProviderError(
                "LLM retry scheduling failed",
                attempts=attempt,
            ) from exc

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code in RETRYABLE_STATUS_CODES or status_code >= 500

    @staticmethod
    def _to_sdk_messages(request: PromptRequest) -> list[ChatCompletionMessageParam]:
        return [
            cast(ChatCompletionMessageParam, {"role": message.role, "content": message.content})
            for message in request.messages
        ]
