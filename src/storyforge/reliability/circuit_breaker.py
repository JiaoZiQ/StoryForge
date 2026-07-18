"""Provider/model circuit breaker with injectable monotonic time."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from storyforge.exceptions import CircuitOpenError


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class CircuitSnapshot:
    state: CircuitState
    failures: int


class CircuitBreaker:
    """Small in-process circuit; state is not distributed between replicas."""

    def __init__(
        self,
        *,
        failure_threshold: int,
        cooldown_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}
        self._half_open_probe: set[str] = set()
        self._lock = threading.Lock()

    def before_call(self, key: str) -> None:
        with self._lock:
            failures = self._failures.get(key, 0)
            if failures < self._threshold:
                return
            opened = self._opened_at.get(key, self._clock())
            if self._clock() - opened < self._cooldown:
                raise CircuitOpenError("Provider circuit is open")
            if key in self._half_open_probe:
                raise CircuitOpenError("Provider circuit half-open probe is already active")
            self._half_open_probe.add(key)

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._opened_at.pop(key, None)
            self._half_open_probe.discard(key)

    def record_failure(self, key: str) -> None:
        with self._lock:
            failures = self._failures.get(key, 0) + 1
            self._failures[key] = failures
            self._half_open_probe.discard(key)
            if failures >= self._threshold:
                self._opened_at[key] = self._clock()

    def snapshot(self, key: str) -> CircuitSnapshot:
        with self._lock:
            failures = self._failures.get(key, 0)
            if failures < self._threshold:
                state = CircuitState.CLOSED
            elif self._clock() - self._opened_at.get(key, 0) >= self._cooldown:
                state = CircuitState.HALF_OPEN
            else:
                state = CircuitState.OPEN
            return CircuitSnapshot(state=state, failures=failures)
