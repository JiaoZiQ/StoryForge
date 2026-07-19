"""Dramatiq transport and Redis notification boundaries."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, Protocol

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from redis import Redis
from redis.client import PubSub
from redis.exceptions import RedisError

from storyforge.exceptions import QueueUnavailableError


class JobBroker(Protocol):
    """Transport only a durable database identifier."""

    def enqueue(
        self, job_id: int, queue_name: str, *, timeout_seconds: int | None = None
    ) -> str: ...

    def ping(self) -> bool: ...


class InMemoryJobBroker:
    """Deterministic transport used by unit tests and inline demos."""

    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []
        self.timeouts: list[int | None] = []

    def enqueue(self, job_id: int, queue_name: str, *, timeout_seconds: int | None = None) -> str:
        self.messages.append((job_id, queue_name))
        self.timeouts.append(timeout_seconds)
        return f"memory-{len(self.messages)}"

    def ping(self) -> bool:
        return True


class DramatiqJobBroker:
    """Redis-backed at-least-once transport with no business result backend."""

    def __init__(self, redis_url: str, *, namespace: str) -> None:
        self._broker = RedisBroker(url=redis_url, namespace=namespace)  # type: ignore[no-untyped-call]

    @property
    def broker(self) -> RedisBroker:
        return self._broker

    def install(self) -> None:
        dramatiq.set_broker(self._broker)

    def enqueue(self, job_id: int, queue_name: str, *, timeout_seconds: int | None = None) -> str:
        suffix = queue_name.rsplit(".", 1)[-1]
        actor_name = {
            "workflow": "storyforge_execute_workflow_job",
            "indexing": "storyforge_execute_indexing_job",
            "book": "storyforge_execute_book_job",
        }.get(suffix, "storyforge_execute_default_job")
        message: dramatiq.Message[Any] = dramatiq.Message(
            queue_name=queue_name,
            actor_name=actor_name,
            args=(job_id,),
            kwargs={},
            options=({"time_limit": timeout_seconds * 1000} if timeout_seconds is not None else {}),
        )
        try:
            self._broker.enqueue(message)
        except RedisError as exc:
            raise QueueUnavailableError("Job broker is unavailable") from exc
        return message.message_id

    def ping(self) -> bool:
        try:
            return bool(self._broker.client.ping())
        except RedisError:
            return False


class RedisEventBus:
    """Ephemeral notification only; PostgreSQL JobEvent remains replay authority."""

    def __init__(self, redis_url: str, *, prefix: str) -> None:
        self._client: Redis = Redis.from_url(redis_url, decode_responses=True)
        self._prefix = prefix

    def publish(self, job_id: int, event_id: int) -> None:
        try:
            self._client.publish(
                self._channel(job_id),
                json.dumps({"job_id": job_id, "event_id": event_id}),
            )
        except RedisError as exc:
            raise QueueUnavailableError("Job event notification is unavailable") from exc

    def listen(self, job_id: int, *, timeout_seconds: float) -> Iterator[int]:
        pubsub: PubSub = self._client.pubsub(  # type: ignore[no-untyped-call]
            ignore_subscribe_messages=True
        )
        pubsub.subscribe(self._channel(job_id))
        try:
            while True:
                item = pubsub.get_message(timeout=timeout_seconds)
                if item is None:
                    yield 0
                    continue
                raw = item.get("data")
                if not isinstance(raw, str):
                    continue
                payload = json.loads(raw)
                event_id = payload.get("event_id")
                if isinstance(event_id, int):
                    yield event_id
        finally:
            pubsub.close()

    def wait_once(self, job_id: int, *, timeout_seconds: float) -> int | None:
        """Wait for one best-effort wake-up without making Redis replay authority."""
        pubsub: PubSub = self._client.pubsub(  # type: ignore[no-untyped-call]
            ignore_subscribe_messages=True
        )
        pubsub.subscribe(self._channel(job_id))
        try:
            item = pubsub.get_message(timeout=timeout_seconds)
            if item is None:
                return None
            raw = item.get("data")
            if not isinstance(raw, str):
                return None
            payload = json.loads(raw)
            event_id = payload.get("event_id")
            return event_id if isinstance(event_id, int) else None
        except (RedisError, json.JSONDecodeError):
            return None
        finally:
            pubsub.close()

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except RedisError:
            return False

    def _channel(self, job_id: int) -> str:
        return f"{self._prefix}:jobs:{job_id}:events"
