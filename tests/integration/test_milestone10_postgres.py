"""PostgreSQL concurrency acceptance for Milestone 10 governance."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from pydantic import BaseModel
from sqlalchemy import Engine, make_url, select, text

from storyforge.database import create_database_engine, create_session_factory
from storyforge.enums import BudgetPeriod
from storyforge.exceptions import BudgetBlockedError, IdempotencyConflictError
from storyforge.llm import MockLLMProvider
from storyforge.llm.types import LLMMessage, LLMResponse, PromptReference, PromptRequest
from storyforge.models import Base, ProjectBudget, ProviderIdempotencyRecord
from storyforge.providers import (
    GovernedLLMProvider,
    ModelRouter,
    ProviderCallContext,
    build_provider_registry,
)
from storyforge.reliability import CircuitBreaker, ProviderRateLimiter, RetryPolicy
from storyforge.schemas.domain import ProjectCreate
from storyforge.services import ProjectService
from storyforge.settings import Settings
from storyforge.usage import BudgetService
from storyforge.usage.repositories import ProviderCallRepository

pytestmark = pytest.mark.postgres
ROOT = Path(__file__).resolve().parents[2]


class _Result(BaseModel):
    ok: bool


class _BlockingProvider:
    """Hold the single raw call open so a concurrent duplicate can be rejected."""

    provider_name = "mock"

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()
        self.call_count = 0

    def generate(self, request: PromptRequest, response_model: type[BaseModel]) -> LLMResponse[Any]:
        with self._lock:
            self.call_count += 1
        self.started.set()
        if not self.release.wait(timeout=10):
            raise TimeoutError("PostgreSQL idempotency test did not release the provider")
        return LLMResponse(
            output=response_model.model_validate({"ok": True}),
            provider=self.provider_name,
            model="mock-storyforge-v1",
            prompt=request.prompt,
            attempts=1,
        )


def _test_url() -> str:
    value = os.getenv("STORYFORGE_POSTGRES_TEST_URL", "")
    if not value:
        pytest.skip("STORYFORGE_POSTGRES_TEST_URL is not configured")
    if not (make_url(value).database or "").casefold().endswith("_test"):
        pytest.fail("PostgreSQL tests require a database name ending in '_test'")
    return value


@pytest.fixture(scope="module")
def pg_engine() -> Iterator[Engine]:
    database_url = _test_url()
    os.environ["DATABASE_URL"] = database_url
    config = Config(str(ROOT / "alembic.ini"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_database_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()
        command.downgrade(config, "base")


@pytest.fixture(autouse=True)
def clean_database(pg_engine: Engine) -> Iterator[None]:
    tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    with pg_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    yield


def _project(engine: Engine, title: str) -> tuple[int, Settings]:
    settings = Settings(environment="test", database_url=_test_url())
    project = ProjectService(create_session_factory(engine)).create(
        ProjectCreate(
            title=title,
            genre="test",
            premise="concurrent provider governance",
            target_chapters=1,
            target_words_per_chapter=100,
        )
    )
    return project.id, settings


def _gateway(
    engine: Engine,
    project_id: int,
    settings: Settings,
    primary: Any,
) -> GovernedLLMProvider:
    session_factory = create_session_factory(engine)
    registry = build_provider_registry(settings)
    return GovernedLLMProvider(
        session_factory=session_factory,
        providers={
            ("mock", "mock-storyforge-v1"): primary,
            ("mock", "mock-storyforge-fallback-v1"): MockLLMProvider({_Result: _Result(ok=True)}),
        },
        registry=registry,
        router=ModelRouter(registry, settings),
        context=ProviderCallContext(project_id=project_id),
        budget=BudgetService(session_factory, settings),
        rate_limiter=ProviderRateLimiter(
            requests_per_minute=100,
            tokens_per_minute=1_000_000,
            max_concurrency=4,
        ),
        circuit_breaker=CircuitBreaker(failure_threshold=3, cooldown_seconds=30),
        retry_policy=RetryPolicy(max_retries=0),
        sleeper=lambda _: None,
    )


def test_concurrent_budget_reservations_never_cross_hard_limit(pg_engine: Engine) -> None:
    project_id, settings = _project(pg_engine, "Concurrent budget")
    session_factory = create_session_factory(pg_engine)
    service = BudgetService(session_factory, settings)
    service.set(
        project_id,
        soft_limit=Decimal("0.50"),
        hard_limit=Decimal("1.00"),
        currency="USD",
        period=BudgetPeriod.LIFETIME,
        enabled=True,
    )
    barrier = threading.Barrier(2)

    def reserve() -> str:
        barrier.wait(timeout=5)
        try:
            BudgetService(session_factory, settings).reserve(project_id, Decimal("0.75"))
        except BudgetBlockedError:
            return "blocked"
        return "reserved"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(reserve) for _index in range(2)]
        results = [future.result(timeout=10) for future in futures]
    assert sorted(results) == ["blocked", "reserved"]
    with session_factory() as session:
        budget = session.scalar(select(ProjectBudget).where(ProjectBudget.project_id == project_id))
        assert budget is not None
        assert budget.reserved_estimated == Decimal("0.75000000")
        assert budget.spent_estimated + budget.reserved_estimated <= budget.hard_limit


def test_concurrent_identical_key_executes_raw_provider_once(pg_engine: Engine) -> None:
    project_id, settings = _project(pg_engine, "Concurrent idempotency")
    session_factory = create_session_factory(pg_engine)
    raw = _BlockingProvider()
    first = _gateway(pg_engine, project_id, settings, raw)
    second = _gateway(pg_engine, project_id, settings, raw)
    request = PromptRequest(
        prompt=PromptReference("provider.smoke", "v1"),
        messages=(
            # The exact same request and context must produce the same persisted key.
            LLMMessage("user", "minimal concurrent request"),
        ),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(first.generate, request, _Result)
        assert raw.started.wait(timeout=5)
        duplicate_future = executor.submit(second.generate, request, _Result)
        with pytest.raises(IdempotencyConflictError):
            duplicate_future.result(timeout=5)
        raw.release.set()
        assert first_future.result(timeout=10).output.ok

    assert raw.call_count == 1
    with session_factory() as session:
        assert len(ProviderCallRepository(session).for_project(project_id)) == 1
        assert len(session.scalars(select(ProviderIdempotencyRecord)).all()) == 1
