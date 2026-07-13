"""Unified structured-output provider contract."""

from typing import Protocol

from storyforge.llm.types import LLMResponse, PromptRequest, ResponseT


class LLMProvider(Protocol):
    """Contract implemented by local and remote structured LLM providers."""

    @property
    def provider_name(self) -> str:
        """Return a stable provider identifier for logs and persisted metadata."""
        ...

    def generate(
        self,
        request: PromptRequest,
        response_model: type[ResponseT],
    ) -> LLMResponse[ResponseT]:
        """Return output validated against the requested Pydantic model."""
        ...
