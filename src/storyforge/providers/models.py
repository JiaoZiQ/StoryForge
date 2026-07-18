"""Validated public and internal provider-registry models."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from storyforge.enums import TaskType


class ModelReference(BaseModel):
    """Stable registry identity for one model."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)

    @property
    def key(self) -> tuple[str, str]:
        return (self.provider, self.model)


class ModelCapability(ModelReference):
    """Capabilities and immutable pricing snapshot source for a registered model."""

    model_type: Literal["chat", "embedding"]
    context_window: int = Field(gt=0)
    max_output_tokens: int = Field(ge=0)
    supports_structured_output: bool = False
    supports_json_schema: bool = False
    supports_tool_calling: bool = False
    supports_batch: bool = False
    supports_embeddings: bool = False
    embedding_dimensions: int | None = Field(default=None, gt=0)
    input_cost_per_million: Decimal | None = Field(default=None, ge=0)
    output_cost_per_million: Decimal | None = Field(default=None, ge=0)
    cached_input_cost_per_million: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    pricing_version: str | None = None
    pricing_effective_date: date | None = None
    enabled: bool = True
    external: bool = False

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        if self.model_type == "embedding":
            if not self.supports_embeddings or self.embedding_dimensions is None:
                raise ValueError("Embedding models require dimensions and embedding capability")
        elif self.supports_embeddings or self.embedding_dimensions is not None:
            raise ValueError("Chat models cannot declare embedding dimensions")
        if self.supports_json_schema and not self.supports_structured_output:
            raise ValueError("JSON schema support requires structured output support")
        prices = (
            self.input_cost_per_million,
            self.output_cost_per_million,
            self.cached_input_cost_per_million,
        )
        if any(price is not None for price in prices) and not (
            self.pricing_version and self.pricing_effective_date
        ):
            raise ValueError("Known pricing requires a version and effective date")
        return self

    @property
    def pricing_known(self) -> bool:
        if self.model_type == "embedding":
            return self.input_cost_per_million is not None
        return self.input_cost_per_million is not None and self.output_cost_per_million is not None


class ModelRoute(BaseModel):
    """One task's controlled primary/fallback route."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_type: TaskType
    primary_model: ModelReference
    fallback_models: tuple[ModelReference, ...] = ()
    max_input_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)
    retry_policy: str = "default"
    budget_policy: str = "project_and_workflow"

    @model_validator(mode="after")
    def validate_route(self) -> Self:
        keys = [self.primary_model.key, *(item.key for item in self.fallback_models)]
        if len(keys) != len(set(keys)):
            raise ValueError("Model route contains a fallback loop or duplicate")
        return self


class ProviderHealth(BaseModel):
    """Secret-free provider health projection."""

    provider: str
    model: str
    enabled: bool
    health_status: Literal["healthy", "configured", "disabled", "unavailable"]
    circuit_status: Literal["closed", "open", "half_open"] = "closed"
    pricing_available: bool
    capabilities: tuple[str, ...]
