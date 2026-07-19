"""Deterministic task-to-capability routing."""

from __future__ import annotations

from storyforge.enums import ModelProfile, TaskType
from storyforge.exceptions import ConfigurationError
from storyforge.providers.models import ModelReference, ModelRoute
from storyforge.providers.registry import ProviderRegistry
from storyforge.settings import Settings

_PROMPT_TASKS = {
    "planner": TaskType.PLANNING,
    "writer": TaskType.CHAPTER_DRAFTING,
    "fact_extractor": TaskType.FACT_EXTRACTION,
    "critic": TaskType.LITERARY_CRITIQUE,
    "revision": TaskType.REVISION,
    "book_critic": TaskType.BOOK_CRITIQUE,
    "provider.smoke": TaskType.LITERARY_CRITIQUE,
}


def task_for_prompt(prompt_name: str) -> TaskType:
    try:
        return _PROMPT_TASKS[prompt_name]
    except KeyError as exc:
        raise ConfigurationError(f"No model task is registered for prompt {prompt_name}") from exc


class ModelRouter:
    """Resolve only predefined profiles to registered compatible models."""

    def __init__(self, registry: ProviderRegistry, settings: Settings) -> None:
        self._registry = registry
        self._settings = settings

    def route(self, task_type: TaskType, profile: ModelProfile) -> ModelRoute:
        is_embedding = task_type in {TaskType.EMBEDDING_DOCUMENT, TaskType.EMBEDDING_QUERY}
        if is_embedding:
            primary = ModelReference(
                provider=self._settings.embedding_provider,
                model=self._settings.embedding_model,
            )
            fallback: tuple[ModelReference, ...] = ()
        elif profile is ModelProfile.OFFLINE or self._settings.llm_provider == "mock":
            primary = ModelReference(provider="mock", model="mock-storyforge-v1")
            fallback = (ModelReference(provider="mock", model="mock-storyforge-fallback-v1"),)
        else:
            primary = ModelReference(
                provider=self._settings.llm_provider,
                model=self._settings.llm_model,
            )
            fallback = ()

        primary_capability = self._registry.get(primary)
        expected_type = "embedding" if is_embedding else "chat"
        if primary_capability.model_type != expected_type:
            raise ConfigurationError("Selected model capability does not match task type")
        if not is_embedding and not primary_capability.supports_structured_output:
            raise ConfigurationError("Selected chat model lacks structured output support")
        if is_embedding and (
            primary_capability.embedding_dimensions != self._settings.embedding_dimensions
        ):
            raise ConfigurationError("Selected embedding model dimensions do not match settings")
        for reference in fallback:
            capability = self._registry.get(reference)
            if capability.model_type != expected_type:
                raise ConfigurationError("Fallback capability does not match task type")
            if not is_embedding and not capability.supports_structured_output:
                raise ConfigurationError("Fallback chat model lacks structured output support")
            if is_embedding and (
                capability.embedding_dimensions != self._settings.embedding_dimensions
            ):
                raise ConfigurationError(
                    "Fallback embedding model dimensions do not match settings"
                )
        return ModelRoute(
            task_type=task_type,
            primary_model=primary,
            fallback_models=fallback,
            max_input_tokens=min(primary_capability.context_window, 128_000),
            max_output_tokens=(
                self._settings.llm_max_output_tokens
                if not is_embedding
                else max(1, primary_capability.context_window)
            ),
            timeout_seconds=(
                self._settings.llm_timeout_seconds
                if not is_embedding
                else self._settings.embedding_timeout_seconds
            ),
        )
