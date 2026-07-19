"""Redis-backed cross-process rate limiting and circuit state."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

from redis import Redis
from redis.exceptions import RedisError

from storyforge.exceptions import CircuitOpenError, ProviderRateLimitError
from storyforge.reliability.circuit_breaker import CircuitBreaker, CircuitSnapshot, CircuitState
from storyforge.reliability.rate_limit import ProviderRateLimiter

logger = logging.getLogger(__name__)

_ADMIT = """
local requests = redis.call('INCR', KEYS[1])
if requests == 1 then redis.call('EXPIRE', KEYS[1], 60) end
local tokens = redis.call('INCRBY', KEYS[2], ARGV[1])
if tokens == tonumber(ARGV[1]) then redis.call('EXPIRE', KEYS[2], 60) end
local active = redis.call('INCR', KEYS[3])
redis.call('EXPIRE', KEYS[3], 120)
if requests > tonumber(ARGV[2]) or tokens > tonumber(ARGV[3]) or active > tonumber(ARGV[4]) then
  redis.call('DECR', KEYS[3]); return 0
end
return 1
"""


class RedisProviderRateLimiter(ProviderRateLimiter):
    """Atomic fixed-window RPM/TPM and concurrency admission shared by replicas."""

    def __init__(
        self,
        redis_url: str,
        *,
        prefix: str,
        requests_per_minute: int,
        tokens_per_minute: int,
        max_concurrency: int,
    ) -> None:
        super().__init__(
            requests_per_minute=requests_per_minute,
            tokens_per_minute=tokens_per_minute,
            max_concurrency=max_concurrency,
        )
        self._client: Redis = Redis.from_url(redis_url, decode_responses=True)
        self._prefix = prefix
        self._rpm = requests_per_minute
        self._tpm = tokens_per_minute
        self._concurrency = max_concurrency

    @contextmanager
    def acquire(self, key: str, *, estimated_tokens: int) -> Iterator[None]:
        base = f"{self._prefix}:rate:{key}"
        try:
            admitted = self._client.eval(
                _ADMIT,
                3,
                f"{base}:rpm",
                f"{base}:tpm",
                f"{base}:active",
                estimated_tokens,
                self._rpm,
                self._tpm,
                self._concurrency,
            )
        except RedisError as exc:
            raise ProviderRateLimitError("Distributed rate limiter is unavailable") from exc
        if int(admitted or 0) != 1:
            raise ProviderRateLimitError("Distributed provider capacity is exhausted")
        try:
            yield
        finally:
            try:
                self._client.eval(
                    "local v=redis.call('GET',KEYS[1]); if v and tonumber(v)>0 then return redis.call('DECR',KEYS[1]) end return 0",
                    1,
                    f"{base}:active",
                )
            except RedisError:
                logger.warning("distributed_rate_limit_release_failed")


class RedisCircuitBreaker(CircuitBreaker):
    """Shared failure/open state; half-open probe ownership is atomic in Redis."""

    def __init__(
        self, redis_url: str, *, prefix: str, failure_threshold: int, cooldown_seconds: float
    ) -> None:
        super().__init__(failure_threshold=failure_threshold, cooldown_seconds=cooldown_seconds)
        self._client: Redis = Redis.from_url(redis_url, decode_responses=True)
        self._prefix = prefix
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds

    def _key(self, key: str) -> str:
        return f"{self._prefix}:circuit:{key}"

    def before_call(self, key: str) -> None:
        now = time.time()
        script = """
local failures=tonumber(redis.call('HGET',KEYS[1],'failures') or '0')
if failures < tonumber(ARGV[1]) then return 1 end
local opened=tonumber(redis.call('HGET',KEYS[1],'opened_at') or ARGV[2])
if tonumber(ARGV[2])-opened < tonumber(ARGV[3]) then return 0 end
if redis.call('HSETNX',KEYS[1],'probe',ARGV[4]) == 0 then return 0 end
redis.call('EXPIRE',KEYS[1],math.ceil(tonumber(ARGV[3])*4)); return 1
"""
        try:
            allowed = self._client.eval(
                script,
                1,
                self._key(key),
                self._threshold,
                now,
                self._cooldown,
                f"{now}:{id(self)}",
            )
        except RedisError as exc:
            raise CircuitOpenError("Distributed circuit state is unavailable") from exc
        if int(allowed or 0) != 1:
            raise CircuitOpenError("Provider circuit is open")

    def record_success(self, key: str) -> None:
        try:
            self._client.delete(self._key(key))
        except RedisError as exc:
            raise CircuitOpenError("Distributed circuit state is unavailable") from exc

    def record_failure(self, key: str) -> None:
        script = """
local failures=redis.call('HINCRBY',KEYS[1],'failures',1)
redis.call('HDEL',KEYS[1],'probe')
if failures >= tonumber(ARGV[1]) then redis.call('HSET',KEYS[1],'opened_at',ARGV[2]) end
redis.call('EXPIRE',KEYS[1],math.ceil(tonumber(ARGV[3])*4)); return failures
"""
        try:
            self._client.eval(
                script, 1, self._key(key), self._threshold, time.time(), self._cooldown
            )
        except RedisError as exc:
            raise CircuitOpenError("Distributed circuit state is unavailable") from exc

    def snapshot(self, key: str) -> CircuitSnapshot:
        try:
            values = cast(dict[str, Any], self._client.hgetall(self._key(key)))
        except RedisError as exc:
            raise CircuitOpenError("Distributed circuit state is unavailable") from exc
        failures = int(values.get("failures", 0))
        if failures < self._threshold:
            state = CircuitState.CLOSED
        elif time.time() - float(values.get("opened_at", 0)) >= self._cooldown:
            state = CircuitState.HALF_OPEN
        else:
            state = CircuitState.OPEN
        return CircuitSnapshot(state=state, failures=failures)
