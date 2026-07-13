"""Shared typed invocation plumbing for StoryForge agents."""

from dataclasses import dataclass
from time import perf_counter

from pydantic import BaseModel

from storyforge.exceptions import AgentExecutionError
from storyforge.llm import LLMMessage, LLMProvider, PromptReference, PromptRegistry, PromptRequest
from storyforge.llm.exceptions import LLMError


@dataclass(frozen=True, slots=True)
class AgentResult[OutputT: BaseModel]:
    """Validated agent output plus reproducibility metadata."""

    output: OutputT
    provider: str
    model: str
    prompt_versions: dict[str, str]
    attempts: int
    duration_ms: int


class StructuredAgent:
    """Render a two-part prompt and invoke the unified LLM boundary."""

    prompt_name: str

    def __init__(self, provider: LLMProvider, registry: PromptRegistry) -> None:
        self._provider = provider
        self._registry = registry

    @property
    def provider_name(self) -> str:
        """Expose only the stable provider identifier for audit metadata."""
        return self._provider.provider_name

    def prompt_versions(self) -> dict[str, str]:
        """Return the prompt versions that the next invocation will render."""
        system = self._registry.render(f"{self.prompt_name}.system")
        user = self._registry.render(f"{self.prompt_name}.user", variables={"payload": "{}"})
        return {
            system.prompt.name: system.prompt.version,
            user.prompt.name: user.prompt.version,
        }

    def _invoke[OutputT: BaseModel](
        self,
        payload: BaseModel,
        response_model: type[OutputT],
    ) -> AgentResult[OutputT]:
        system = self._registry.render(f"{self.prompt_name}.system")
        user = self._registry.render(
            f"{self.prompt_name}.user",
            variables={"payload": payload.model_dump_json(indent=2)},
        )
        prompt_versions = {
            system.prompt.name: system.prompt.version,
            user.prompt.name: user.prompt.version,
        }
        request = PromptRequest(
            prompt=PromptReference(
                name=self.prompt_name,
                version=",".join(f"{key}={value}" for key, value in prompt_versions.items()),
            ),
            messages=tuple(
                LLMMessage(role=message.role, content=message.content)
                for message in (*system.messages, *user.messages)
            ),
        )
        started = perf_counter()
        try:
            response = self._provider.generate(request, response_model)
        except LLMError as exc:
            raise AgentExecutionError(
                f"{self.prompt_name} agent failed to produce valid structured output"
            ) from exc
        duration_ms = max(0, round((perf_counter() - started) * 1000))
        return AgentResult(
            output=response.output,
            provider=response.provider,
            model=response.model,
            prompt_versions=prompt_versions,
            attempts=response.attempts,
            duration_ms=duration_ms,
        )
