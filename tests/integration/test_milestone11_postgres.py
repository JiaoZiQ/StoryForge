"""PostgreSQL concurrency acceptance for the Milestone 11 queue."""

from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, make_url, select, text

from storyforge.application import JobApplicationService
from storyforge.database import create_database_engine, create_session_factory
from storyforge.enums import JobType
from storyforge.exceptions import CircuitOpenError, ProviderRateLimitError
from storyforge.jobs.broker import InMemoryJobBroker
from storyforge.jobs.dispatcher import OutboxDispatcher
from storyforge.models import Base, Job, OutboxMessage
from storyforge.reliability.distributed import RedisCircuitBreaker, RedisProviderRateLimiter
from storyforge.schemas.domain import ProjectCreate
from storyforge.schemas.jobs import JobCreateRequest
from storyforge.services import ProjectService
from storyforge.settings import Settings

pytestmark = pytest.mark.postgres
ROOT = Path(__file__).resolve().parents[2]


def _test_url() -> str:
    value = os.getenv("STORYFORGE_POSTGRES_TEST_URL", "")
    if not value:
        pytest.skip("STORYFORGE_POSTGRES_TEST_URL is not configured")
    if not (make_url(value).database or "").casefold().endswith("_test"):
        pytest.fail("PostgreSQL tests require a database name ending in '_test'")
    return value


@pytest.fixture(scope="module")
def pg_engine() -> Iterator[Engine]:
    url = _test_url()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    config = Config(str(ROOT / "alembic.ini"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_database_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()
        command.downgrade(config, "base")
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture(autouse=True)
def clean_database(pg_engine: Engine) -> Iterator[None]:
    tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    with pg_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    yield


def _runtime(pg_engine: Engine) -> tuple[JobApplicationService, Settings, int]:
    sessions = create_session_factory(pg_engine)
    settings = Settings(
        environment="test",
        database_url=_test_url(),
        job_execution_mode="inline",
        queue_pending_hard_limit=1000,
        project_pending_limit=1000,
    )
    project = ProjectService(sessions).create(
        ProjectCreate(
            title="M11 PostgreSQL",
            genre="test",
            premise="Concurrent queue safety",
            target_chapters=1,
            target_words_per_chapter=100,
        )
    )
    return JobApplicationService(sessions, settings), settings, project.id


def _request(project_id: int, key: str) -> JobCreateRequest:
    return JobCreateRequest(
        job_type=JobType.RUN_RETRIEVAL_WARMUP,
        project_id=project_id,
        operation="postgres-concurrency",
        payload={"query": "safe", "current_chapter": 1},
        idempotency_key=key,
    )


def test_concurrent_idempotent_create_has_one_job_and_outbox(pg_engine: Engine) -> None:
    service, _, project_id = _runtime(pg_engine)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: service.create(_request(project_id, "same")), range(8)))
    assert len({item.job_id for item in results}) == 1
    sessions = create_session_factory(pg_engine)
    with sessions() as session:
        assert session.scalar(select(func.count(Job.id))) == 1
        assert session.scalar(select(func.count(OutboxMessage.id))) == 1


def test_two_dispatchers_skip_locked_without_duplicate_claim(pg_engine: Engine) -> None:
    service, settings, project_id = _runtime(pg_engine)
    for index in range(20):
        service.create(_request(project_id, f"job-{index}"))
    sessions = create_session_factory(pg_engine)
    broker = InMemoryJobBroker()
    first = OutboxDispatcher(sessions, broker, settings, dispatcher_id="dispatcher-a")
    second = OutboxDispatcher(sessions, broker, settings, dispatcher_id="dispatcher-b")
    with ThreadPoolExecutor(max_workers=2) as pool:
        published = list(pool.map(lambda item: item.dispatch_once(), (first, second)))
    assert sum(published) == 20
    assert len(broker.messages) == 20
    assert len({job_id for job_id, _ in broker.messages}) == 20


def test_redis_rate_and_circuit_state_are_shared_across_workers(pg_engine: Engine) -> None:
    del pg_engine
    redis_url = os.getenv("STORYFORGE_REDIS_URL", "")
    if not redis_url:
        pytest.skip("STORYFORGE_REDIS_URL is not configured")
    prefix = f"m11-test-{uuid4()}"
    limiter_one = RedisProviderRateLimiter(
        redis_url,
        prefix=prefix,
        requests_per_minute=10,
        tokens_per_minute=100,
        max_concurrency=1,
    )
    limiter_two = RedisProviderRateLimiter(
        redis_url,
        prefix=prefix,
        requests_per_minute=10,
        tokens_per_minute=100,
        max_concurrency=1,
    )
    with ExitStack() as stack:
        stack.enter_context(limiter_one.acquire("mock:model:chat", estimated_tokens=10))
        with pytest.raises(ProviderRateLimitError):
            stack.enter_context(limiter_two.acquire("mock:model:chat", estimated_tokens=10))

    circuit_one = RedisCircuitBreaker(
        redis_url, prefix=prefix, failure_threshold=1, cooldown_seconds=30
    )
    circuit_two = RedisCircuitBreaker(
        redis_url, prefix=prefix, failure_threshold=1, cooldown_seconds=30
    )
    circuit_one.record_failure("mock:model")
    with pytest.raises(CircuitOpenError):
        circuit_two.before_call("mock:model")
    circuit_one.record_success("mock:model")
    circuit_two.before_call("mock:model")
