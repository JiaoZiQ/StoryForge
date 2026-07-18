"""Process-local RPM/TPM/concurrency admission without waiting."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from storyforge.exceptions import ProviderRateLimitError


class ProviderRateLimiter:
    """Sliding-window limiter; intentionally not shared across application instances."""

    def __init__(
        self,
        *,
        requests_per_minute: int,
        tokens_per_minute: int,
        max_concurrency: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._rpm = requests_per_minute
        self._tpm = tokens_per_minute
        self._max_concurrency = max_concurrency
        self._clock = clock
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._tokens: dict[str, deque[tuple[float, int]]] = defaultdict(deque)
        self._active: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    @contextmanager
    def acquire(self, key: str, *, estimated_tokens: int) -> Iterator[None]:
        now = self._clock()
        with self._lock:
            cutoff = now - 60.0
            requests = self._requests[key]
            tokens = self._tokens[key]
            while requests and requests[0] <= cutoff:
                requests.popleft()
            while tokens and tokens[0][0] <= cutoff:
                tokens.popleft()
            if len(requests) >= self._rpm:
                raise ProviderRateLimitError("Provider requests-per-minute limit exceeded")
            if sum(value for _, value in tokens) + estimated_tokens > self._tpm:
                raise ProviderRateLimitError("Provider tokens-per-minute limit exceeded")
            if self._active[key] >= self._max_concurrency:
                raise ProviderRateLimitError("Provider concurrency limit exceeded")
            requests.append(now)
            tokens.append((now, estimated_tokens))
            self._active[key] += 1
        try:
            yield
        finally:
            with self._lock:
                self._active[key] = max(0, self._active[key] - 1)
