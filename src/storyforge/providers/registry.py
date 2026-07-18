"""Central model registry loaded from safe settings or explicit JSON."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from storyforge.exceptions import ConfigurationError
from storyforge.providers.models import ModelCapability, ModelReference
from storyforge.settings import Settings


class ProviderRegistry:
    """Validated model capability lookup without secret material."""

    def __init__(self, capabilities: list[ModelCapability]) -> None:
        self._models: dict[tuple[str, str], ModelCapability] = {}
        for capability in capabilities:
            if capability.key in self._models:
                raise ConfigurationError(
                    f"Duplicate provider model registration: {capability.provider}/{capability.model}"
                )
            self._models[capability.key] = capability
        if not self._models:
            raise ConfigurationError("Provider registry must contain at least one model")

    def get(self, reference: ModelReference) -> ModelCapability:
        try:
            capability = self._models[reference.key]
        except KeyError as exc:
            raise ConfigurationError(
                f"Unknown registered model: {reference.provider}/{reference.model}"
            ) from exc
        if not capability.enabled:
            raise ConfigurationError(
                f"Registered model is disabled: {reference.provider}/{reference.model}"
            )
        return capability

    def list(self) -> list[ModelCapability]:
        return sorted(self._models.values(), key=lambda item: item.key)


class _PricingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    input_cost_per_million: Decimal | None = Field(default=None, ge=0)
    output_cost_per_million: Decimal | None = Field(default=None, ge=0)
    cached_input_cost_per_million: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    pricing_version: str = Field(min_length=1)
    pricing_effective_date: date


def _load_models(path: Path) -> list[ModelCapability]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_models = payload["models"] if isinstance(payload, dict) else payload
        return TypeAdapter(list[ModelCapability]).validate_python(raw_models)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValidationError) as exc:
        raise ConfigurationError("Provider registry JSON is invalid") from exc


def _apply_pricing(capabilities: list[ModelCapability], path: Path) -> list[ModelCapability]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_prices = payload["prices"] if isinstance(payload, dict) else payload
        prices = TypeAdapter(list[_PricingUpdate]).validate_python(raw_prices)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValidationError) as exc:
        raise ConfigurationError("Provider pricing JSON is invalid") from exc
    updates = {(item.provider, item.model): item for item in prices}
    if len(updates) != len(prices):
        raise ConfigurationError("Provider pricing contains duplicate model entries")
    known = {item.key for item in capabilities}
    unknown = set(updates) - known
    if unknown:
        provider, model = sorted(unknown)[0]
        raise ConfigurationError(f"Pricing references an unknown model: {provider}/{model}")
    merged: list[ModelCapability] = []
    for capability in capabilities:
        update = updates.get(capability.key)
        if update is None:
            merged.append(capability)
            continue
        merged.append(
            ModelCapability.model_validate(
                {
                    **capability.model_dump(),
                    **update.model_dump(),
                }
            )
        )
    return merged


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    """Build the process registry; never read an API key into registry models."""
    if settings.provider_config_path is not None:
        capabilities = _load_models(settings.provider_config_path)
        if settings.pricing_config_path is not None:
            capabilities = _apply_pricing(capabilities, settings.pricing_config_path)
        return ProviderRegistry(capabilities)

    today = date(2026, 7, 17)
    capabilities = [
        ModelCapability(
            provider="mock",
            model="mock-storyforge-v1",
            model_type="chat",
            context_window=128_000,
            max_output_tokens=16_384,
            supports_structured_output=True,
            supports_json_schema=True,
            supports_tool_calling=False,
            supports_batch=False,
            input_cost_per_million=Decimal("0"),
            output_cost_per_million=Decimal("0"),
            cached_input_cost_per_million=Decimal("0"),
            pricing_version="mock-v1",
            pricing_effective_date=today,
            enabled=True,
            external=False,
        ),
        ModelCapability(
            provider="mock",
            model="mock-storyforge-fallback-v1",
            model_type="chat",
            context_window=256_000,
            max_output_tokens=16_384,
            supports_structured_output=True,
            supports_json_schema=True,
            supports_tool_calling=False,
            supports_batch=False,
            input_cost_per_million=Decimal("0"),
            output_cost_per_million=Decimal("0"),
            cached_input_cost_per_million=Decimal("0"),
            pricing_version="mock-v1",
            pricing_effective_date=today,
            enabled=True,
            external=False,
        ),
        ModelCapability(
            provider="mock",
            model="mock-hash-embedding-v1",
            model_type="embedding",
            context_window=8_192,
            max_output_tokens=0,
            supports_batch=True,
            supports_embeddings=True,
            embedding_dimensions=64,
            input_cost_per_million=Decimal("0"),
            output_cost_per_million=Decimal("0"),
            cached_input_cost_per_million=Decimal("0"),
            pricing_version="mock-v1",
            pricing_effective_date=today,
            enabled=True,
            external=False,
        ),
    ]
    if settings.llm_provider != "mock":
        capabilities.append(
            ModelCapability(
                provider=settings.llm_provider,
                model=settings.llm_model,
                model_type="chat",
                context_window=128_000,
                max_output_tokens=settings.llm_max_output_tokens,
                supports_structured_output=True,
                supports_json_schema=settings.llm_structured_output_mode == "json_schema",
                supports_tool_calling=False,
                supports_batch=False,
                enabled=True,
                external=True,
            )
        )
    if settings.embedding_provider != "mock":
        capabilities.append(
            ModelCapability(
                provider=settings.embedding_provider,
                model=settings.embedding_model,
                model_type="embedding",
                context_window=8_192,
                max_output_tokens=0,
                supports_batch=True,
                supports_embeddings=True,
                embedding_dimensions=settings.embedding_dimensions,
                enabled=True,
                external=True,
            )
        )
    if settings.pricing_config_path is not None:
        capabilities = _apply_pricing(capabilities, settings.pricing_config_path)
    return ProviderRegistry(capabilities)
