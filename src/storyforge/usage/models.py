"""Provider-neutral usage, money, and budget projections."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from storyforge.enums import TokenUsageSource


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(ge=0)
    source: TokenUsageSource

    @model_validator(mode="after")
    def validate_total(self) -> TokenUsage:
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("Total tokens must equal input plus output tokens")
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("Cached input tokens cannot exceed input tokens")
        return self


class PricingSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    model: str
    input_cost_per_million: Decimal | None = None
    output_cost_per_million: Decimal | None = None
    cached_input_cost_per_million: Decimal | None = None
    currency: str = "USD"
    pricing_version: str | None = None
    effective_date: str | None = None

    @property
    def known(self) -> bool:
        return self.input_cost_per_million is not None and self.output_cost_per_million is not None


class PriceEstimate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    amount: Decimal | None
    currency: str
    estimated: bool = True
    snapshot: PricingSnapshot


class BudgetDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    warning: bool
    reason: str
    reserved_amount: Decimal = Decimal("0")


class UsageSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    calls: int = 0
    succeeded: int = 0
    failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: Decimal | None = Decimal("0")
    billed_cost: Decimal | None = None
    fallback_count: int = 0
    timeout_count: int = 0
    rate_limit_count: int = 0
    average_latency_ms: Decimal = Decimal("0")
    currency: str = "USD"
