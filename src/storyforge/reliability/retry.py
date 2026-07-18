"""Injectable bounded retry classification and backoff."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from storyforge.exceptions import (
    BudgetBlockedError,
    CircuitOpenError,
    PrivacyPolicyError,
    ProviderRateLimitError,
)
from storyforge.llm.exceptions import (
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMServiceError,
    LLMTimeoutError,
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_retries: int = 2
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 10.0
    jitter_ratio: float = 0.1
    random_source: Callable[[], float] = random.random

    def retryable(self, error: BaseException) -> bool:
        if isinstance(
            error,
            (
                LLMAuthenticationError,
                LLMRefusalError,
                BudgetBlockedError,
                PrivacyPolicyError,
                ProviderRateLimitError,
                CircuitOpenError,
            ),
        ):
            return False
        return isinstance(error, (LLMTimeoutError, LLMRateLimitError, LLMServiceError))

    def delay(self, retry_index: int, retry_after: float | None = None) -> float:
        if retry_after is not None:
            return min(self.max_delay_seconds, max(0.0, retry_after))
        base = min(self.max_delay_seconds, self.base_delay_seconds * (2**retry_index))
        jitter = base * self.jitter_ratio * self.random_source()
        return float(min(self.max_delay_seconds, base + jitter))
