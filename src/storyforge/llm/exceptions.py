"""Project-owned exceptions for prompt and LLM provider boundaries."""


class LLMError(Exception):
    """Base class for every error exposed by the StoryForge LLM boundary."""


class LLMConfigurationError(LLMError):
    """Raised when a provider is configured with missing or invalid values."""


class PromptRegistryError(LLMError):
    """Raised when prompt registration or rendering fails."""


class LLMProviderError(LLMError):
    """Base class for failures produced while invoking an LLM provider."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.status_code = status_code


class LLMTimeoutError(LLMProviderError):
    """Raised when a provider request exhausts its timeout retries."""


class LLMAuthenticationError(LLMProviderError):
    """Raised when the provider rejects its credentials."""


class LLMRateLimitError(LLMProviderError):
    """Raised when provider rate-limit retries are exhausted."""


class LLMServiceError(LLMProviderError):
    """Raised for provider transport or non-success status failures."""


class LLMInvalidResponseError(LLMProviderError):
    """Raised when structured output cannot be parsed or validated."""


class LLMRefusalError(LLMProviderError):
    """Raised when the model explicitly refuses the request."""
