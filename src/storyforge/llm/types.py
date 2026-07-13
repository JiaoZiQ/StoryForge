"""Typed values shared by all StoryForge LLM providers."""

from dataclasses import dataclass
from typing import Literal, TypeVar

from pydantic import BaseModel

ResponseT = TypeVar("ResponseT", bound=BaseModel)
MessageRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """One minimal message passed across the LLM boundary."""

    role: MessageRole
    content: str

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("LLM message content must not be empty")


@dataclass(frozen=True, slots=True)
class PromptReference:
    """Stable identity of the exact prompt template used for a request."""

    name: str
    version: str

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip():
            raise ValueError("Prompt name and version must not be empty")


@dataclass(frozen=True, slots=True)
class PromptRequest:
    """Rendered, versioned prompt ready for a provider call."""

    prompt: PromptReference
    messages: tuple[LLMMessage, ...]

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("A prompt request must contain at least one message")


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Provider-neutral token accounting when returned by the API."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class LLMResponse[ResponseT: BaseModel]:
    """Validated provider output plus reproducibility metadata."""

    output: ResponseT
    provider: str
    model: str
    prompt: PromptReference
    attempts: int
    usage: TokenUsage | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("LLM response attempts must be positive")
