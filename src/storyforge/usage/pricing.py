"""Decimal-only token estimation and immutable price calculation."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

from storyforge.enums import TokenUsageSource
from storyforge.providers.models import ModelCapability
from storyforge.usage.models import PriceEstimate, PricingSnapshot, TokenUsage

_MILLION = Decimal("1000000")
_QUANTUM = Decimal("0.00000001")


def estimate_tokens(text: str) -> int:
    """Conservative local estimate; it is never represented as provider-reported usage."""
    if not text:
        return 0
    cjk = sum("\u3400" <= char <= "\u9fff" for char in text)
    other = len(text) - cjk
    return max(1, cjk + math.ceil(other / 4))


class PricingService:
    """Calculate an estimated price from a capability's versioned snapshot."""

    @staticmethod
    def snapshot(capability: ModelCapability) -> PricingSnapshot:
        return PricingSnapshot(
            provider=capability.provider,
            model=capability.model,
            input_cost_per_million=capability.input_cost_per_million,
            output_cost_per_million=capability.output_cost_per_million,
            cached_input_cost_per_million=capability.cached_input_cost_per_million,
            currency=capability.currency,
            pricing_version=capability.pricing_version,
            effective_date=(
                capability.pricing_effective_date.isoformat()
                if capability.pricing_effective_date is not None
                else None
            ),
        )

    def estimate(self, capability: ModelCapability, usage: TokenUsage) -> PriceEstimate:
        snapshot = self.snapshot(capability)
        if capability.input_cost_per_million is None:
            return PriceEstimate(amount=None, currency=capability.currency, snapshot=snapshot)
        if usage.output_tokens and capability.output_cost_per_million is None:
            return PriceEstimate(amount=None, currency=capability.currency, snapshot=snapshot)
        uncached_input = usage.input_tokens - usage.cached_input_tokens
        cached_rate = capability.cached_input_cost_per_million
        if usage.cached_input_tokens and cached_rate is None:
            cached_rate = capability.input_cost_per_million
        amount = Decimal(uncached_input) * capability.input_cost_per_million / _MILLION
        amount += Decimal(usage.cached_input_tokens) * (cached_rate or Decimal("0")) / _MILLION
        amount += (
            Decimal(usage.output_tokens)
            * (capability.output_cost_per_million or Decimal("0"))
            / _MILLION
        )
        return PriceEstimate(
            amount=amount.quantize(_QUANTUM, rounding=ROUND_HALF_UP),
            currency=capability.currency,
            snapshot=snapshot,
        )

    @staticmethod
    def local_usage(input_text: str, output_text: str = "") -> TokenUsage:
        input_tokens = estimate_tokens(input_text)
        output_tokens = estimate_tokens(output_text)
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            source=TokenUsageSource.LOCAL_ESTIMATE,
        )
