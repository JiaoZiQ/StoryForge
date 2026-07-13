"""Structured LLM provider boundary for StoryForge."""

from storyforge.llm.exceptions import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMError,
    LLMInvalidResponseError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMServiceError,
    LLMTimeoutError,
    PromptRegistryError,
)
from storyforge.llm.mock import MockFailure, MockLLMProvider
from storyforge.llm.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
)
from storyforge.llm.prompts import PromptMessageTemplate, PromptRegistry, PromptTemplate
from storyforge.llm.provider import LLMProvider
from storyforge.llm.types import (
    LLMMessage,
    LLMResponse,
    PromptReference,
    PromptRequest,
    TokenUsage,
)

__all__ = [
    "LLMAuthenticationError",
    "LLMConfigurationError",
    "LLMError",
    "LLMInvalidResponseError",
    "LLMMessage",
    "LLMProvider",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMRefusalError",
    "LLMResponse",
    "LLMServiceError",
    "LLMTimeoutError",
    "MockFailure",
    "MockLLMProvider",
    "OpenAICompatibleConfig",
    "OpenAICompatibleProvider",
    "PromptMessageTemplate",
    "PromptReference",
    "PromptRegistry",
    "PromptRegistryError",
    "PromptRequest",
    "PromptTemplate",
    "TokenUsage",
]
