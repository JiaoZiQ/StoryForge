"""PostgreSQL, MockLLM, network-free provider governance demonstration."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import make_url, select, text

from storyforge.database import (
    SessionFactory,
    create_database_engine,
    create_session_factory,
    normalize_database_url,
)
from storyforge.enums import BudgetPeriod, ModelProfile, PrivacyPolicy, ProviderCallStatus
from storyforge.exceptions import (
    BudgetBlockedError,
    ConfigurationError,
    IdempotencyConflictError,
    InvalidStateError,
)
from storyforge.llm import MockFailure, MockLLMProvider
from storyforge.llm.types import LLMMessage, PromptReference, PromptRequest
from storyforge.m8_demo import run_demo_m8
from storyforge.models import ProviderCall
from storyforge.providers import (
    GovernedLLMProvider,
    ModelRouter,
    ProviderCallContext,
    ProviderRegistry,
    build_provider_registry,
)
from storyforge.reliability import CircuitBreaker, ProviderRateLimiter, RetryPolicy
from storyforge.schemas.domain import ProjectCreate
from storyforge.schemas.governance import (
    DemoM10Response,
    DemoM10ScenarioA,
    DemoM10ScenarioB,
    DemoM10ScenarioC,
    DemoM10ScenarioD,
    DemoM10ScenarioE,
    DemoM10ScenarioF,
)
from storyforge.services import ProjectService
from storyforge.settings import Settings
from storyforge.usage import BudgetService, UsageService
from storyforge.usage.repositories import ProviderCallRepository


class _Probe(BaseModel):
    ok: bool


class _ManualClock:
    """Deterministic monotonic clock used by every reliability primitive in the demo."""

    def __init__(self) -> None:
        self._value = 0.0

    def __call__(self) -> float:
        return self._value

    def sleep(self, seconds: float) -> None:
        self._value += max(0.0, seconds)


def run_demo_m10(settings: Settings | None = None) -> DemoM10Response:
    """Exercise success, retry, fallback, circuit, budget, and idempotency offline."""
    configured = settings or Settings.from_env()
    backend = make_url(normalize_database_url(configured.database_url)).get_backend_name()
    if backend != "postgresql":
        raise ConfigurationError("demo-m10 requires a PostgreSQL database")
    if configured.llm_provider != "mock" or configured.embedding_provider != "mock":
        raise ConfigurationError("demo-m10 requires MockLLM and MockEmbedding")
    if configured.llm_api_key is not None or configured.embedding_api_key is not None:
        raise ConfigurationError("demo-m10 must run without API keys")

    engine = create_database_engine(configured.database_url)
    try:
        session_factory = create_session_factory(engine)
        with engine.connect() as connection:
            extension = connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
        if not extension:
            raise InvalidStateError("PostgreSQL vector extension is not enabled")

        workflow_demo = run_demo_m8(
            configured,
            model_profile=ModelProfile.BALANCED,
            privacy_policy=PrivacyPolicy.STRICT,
        )
        workflow_usage = UsageService(session_factory, configured.default_currency).summary(
            workflow_demo.project_id
        )
        if not workflow_usage.calls or not workflow_usage.total_tokens:
            raise InvalidStateError("Scenario A did not persist provider usage")
        if workflow_usage.estimated_cost is None:
            raise InvalidStateError("Scenario A mock pricing unexpectedly became unknown")

        project = ProjectService(session_factory).create(
            ProjectCreate(
                title=f"Milestone 10 Reliability {uuid4().hex[:12]}",
                genre="test",
                premise="A content-free provider reliability probe.",
                target_chapters=1,
                target_words_per_chapter=100,
                language="en",
            )
        )
        with session_factory.begin() as session:
            persisted = session.get(type(project), project.id)
            if persisted is None:
                raise InvalidStateError("Reliability project disappeared")
            persisted.model_profile = ModelProfile.BALANCED
            persisted.privacy_policy = PrivacyPolicy.STRICT

        registry = build_provider_registry(configured)
        router = ModelRouter(registry, configured)
        clock = _ManualClock()
        limiter = ProviderRateLimiter(
            requests_per_minute=10_000,
            tokens_per_minute=100_000_000,
            max_concurrency=10,
            clock=clock,
        )
        response = _Probe(ok=True)

        retry_raw = MockLLMProvider({_Probe: response}, failures=(MockFailure.RATE_LIMIT,))
        retry_gateway = _gateway(
            session_factory,
            configured,
            registry,
            router,
            limiter,
            CircuitBreaker(failure_threshold=3, cooldown_seconds=30, clock=clock),
            retry_raw,
            MockLLMProvider({_Probe: response}),
            project.id,
            retries=1,
            clock=clock,
        )
        retry_gateway.generate(_request("retry"), _Probe)
        retry_calls = _calls_for_label(session_factory, project.id, "provider.smoke", 1, 2)
        if [item.status for item in retry_calls] != [
            ProviderCallStatus.RATE_LIMITED,
            ProviderCallStatus.SUCCEEDED,
        ]:
            raise InvalidStateError("Scenario B did not persist a bounded retry")

        fallback_gateway = _gateway(
            session_factory,
            configured,
            registry,
            router,
            limiter,
            CircuitBreaker(failure_threshold=3, cooldown_seconds=30, clock=clock),
            MockLLMProvider({_Probe: response}, failures=(MockFailure.TIMEOUT,)),
            MockLLMProvider({_Probe: response}),
            project.id,
            retries=0,
            clock=clock,
        )
        before_fallback = _call_count(session_factory, project.id)
        fallback_gateway.generate(_request("fallback"), _Probe)
        fallback_calls = _calls_since(session_factory, project.id, before_fallback)
        if len(fallback_calls) != 2 or fallback_calls[-1].fallback_index != 1:
            raise InvalidStateError("Scenario C did not use exactly one fallback")

        circuit = CircuitBreaker(failure_threshold=2, cooldown_seconds=300, clock=clock)
        circuit_gateway = _gateway(
            session_factory,
            configured,
            registry,
            router,
            limiter,
            circuit,
            MockLLMProvider(
                {_Probe: response},
                failures=(MockFailure.SERVER_ERROR, MockFailure.SERVER_ERROR),
            ),
            MockLLMProvider({_Probe: response}),
            project.id,
            retries=0,
            clock=clock,
        )
        circuit_gateway.generate(_request("circuit-1"), _Probe)
        circuit_gateway.generate(_request("circuit-2"), _Probe)
        before_open = _call_count(session_factory, project.id)
        circuit_gateway.generate(_request("circuit-3"), _Probe)
        open_calls = _calls_since(session_factory, project.id, before_open)
        circuit_state = circuit.snapshot("mock/mock-storyforge-v1").state.value
        if circuit_state != "open" or open_calls[-1].fallback_index != 1:
            raise InvalidStateError("Scenario D did not fast-fail to fallback")

        expensive_registry = ProviderRegistry(
            [
                item.model_copy(
                    update={
                        "input_cost_per_million": Decimal("1"),
                        "output_cost_per_million": Decimal("1"),
                        "cached_input_cost_per_million": Decimal("1"),
                        "pricing_version": "demo-v1",
                        "pricing_effective_date": date(2026, 7, 17),
                    }
                )
                if item.model_type == "chat"
                else item
                for item in registry.list()
            ]
        )
        BudgetService(session_factory, configured).set(
            project.id,
            soft_limit=Decimal("0.00000001"),
            hard_limit=Decimal("0.00000002"),
            currency="USD",
            period=BudgetPeriod.LIFETIME,
            enabled=True,
        )
        budget_raw = MockLLMProvider({_Probe: response})
        budget_gateway = _gateway(
            session_factory,
            configured,
            expensive_registry,
            ModelRouter(expensive_registry, configured),
            limiter,
            CircuitBreaker(failure_threshold=3, cooldown_seconds=30, clock=clock),
            budget_raw,
            MockLLMProvider({_Probe: response}),
            project.id,
            retries=0,
            clock=clock,
        )
        try:
            budget_gateway.generate(_request("budget"), _Probe)
        except BudgetBlockedError:
            pass
        else:
            raise InvalidStateError("Scenario E did not block before provider invocation")
        if budget_raw.call_count:
            raise InvalidStateError("Scenario E invoked a provider after budget block")

        BudgetService(session_factory, configured).set(
            project.id,
            soft_limit=Decimal("5"),
            hard_limit=Decimal("10"),
            currency="USD",
            period=BudgetPeriod.LIFETIME,
            enabled=True,
        )
        idempotent_raw = MockLLMProvider({_Probe: response})
        idempotent_gateway = _gateway(
            session_factory,
            configured,
            registry,
            router,
            limiter,
            CircuitBreaker(failure_threshold=3, cooldown_seconds=30, clock=clock),
            idempotent_raw,
            MockLLMProvider({_Probe: response}),
            project.id,
            retries=0,
            clock=clock,
        )
        idempotent_gateway.generate(_request("resume"), _Probe)
        calls_before = _call_count(session_factory, project.id)
        cost_before = _estimated_cost(session_factory, project.id)
        resumed_gateway = _gateway(
            session_factory,
            configured,
            registry,
            router,
            limiter,
            CircuitBreaker(failure_threshold=3, cooldown_seconds=30, clock=clock),
            MockLLMProvider({_Probe: response}),
            MockLLMProvider({_Probe: response}),
            project.id,
            retries=0,
            clock=clock,
        )
        try:
            resumed_gateway.generate(_request("resume"), _Probe)
        except IdempotencyConflictError:
            pass
        else:
            raise InvalidStateError("Scenario F did not reuse the persisted domain artifact")
        calls_after = _call_count(session_factory, project.id)
        cost_after = _estimated_cost(session_factory, project.id)
        if calls_after != calls_before or cost_after != cost_before:
            raise InvalidStateError("Scenario F duplicated provider usage")

        return DemoM10Response(
            database_backend="PostgreSQL",
            project_id=workflow_demo.project_id,
            profile=ModelProfile.BALANCED.value,
            privacy_policy=PrivacyPolicy.STRICT.value,
            scenario_a=DemoM10ScenarioA(
                status=workflow_demo.workflow_status,
                provider_calls=workflow_usage.calls,
                tokens=workflow_usage.total_tokens,
                estimated_cost=workflow_usage.estimated_cost,
            ),
            scenario_b=DemoM10ScenarioB(
                attempts=len(retry_calls),
                retry_reason=ProviderCallStatus.RATE_LIMITED.value,
                status=retry_calls[-1].status.value,
            ),
            scenario_c=DemoM10ScenarioC(
                primary=fallback_calls[0].status.value,
                fallback=fallback_calls[-1].status.value,
                fallback_count=1,
            ),
            scenario_d=DemoM10ScenarioD(circuit=circuit_state, fallback_used=True),
            scenario_e=DemoM10ScenarioE(
                budget_status="blocked", provider_calls_made=budget_raw.call_count
            ),
            scenario_f=DemoM10ScenarioF(
                calls_before_resume=calls_before,
                calls_after_resume=calls_after,
                duplicate_calls=calls_after - calls_before,
                duplicate_cost_records=int(cost_after != cost_before),
            ),
        )
    finally:
        engine.dispose()


def _gateway(
    session_factory: SessionFactory,
    settings: Settings,
    registry: ProviderRegistry,
    router: ModelRouter,
    limiter: ProviderRateLimiter,
    circuit: CircuitBreaker,
    primary: MockLLMProvider,
    fallback: MockLLMProvider,
    project_id: int,
    *,
    retries: int,
    clock: _ManualClock,
) -> GovernedLLMProvider:
    return GovernedLLMProvider(
        session_factory=session_factory,
        providers={
            ("mock", "mock-storyforge-v1"): primary,
            ("mock", "mock-storyforge-fallback-v1"): fallback,
        },
        registry=registry,
        router=router,
        context=ProviderCallContext(
            project_id=project_id,
            profile=ModelProfile.BALANCED,
            privacy_policy=PrivacyPolicy.STRICT,
        ),
        budget=BudgetService(session_factory, settings),
        rate_limiter=limiter,
        circuit_breaker=circuit,
        retry_policy=RetryPolicy(
            max_retries=retries,
            base_delay_seconds=0,
            jitter_ratio=0,
        ),
        sleeper=clock.sleep,
        clock=clock,
    )


def _request(label: str) -> PromptRequest:
    return PromptRequest(
        prompt=PromptReference("provider.smoke", "v1"),
        messages=(LLMMessage("user", f"offline reliability probe {label}"),),
    )


def _call_count(session_factory: SessionFactory, project_id: int) -> int:
    with session_factory() as session:
        return len(ProviderCallRepository(session).for_project(project_id))


def _calls_since(
    session_factory: SessionFactory, project_id: int, before: int
) -> list[ProviderCall]:
    with session_factory() as session:
        calls = ProviderCallRepository(session).for_project(project_id)[before:]
        for item in calls:
            session.expunge(item)
        return calls


def _calls_for_label(
    session_factory: SessionFactory,
    project_id: int,
    _prompt_name: str,
    start: int,
    end: int,
) -> list[ProviderCall]:
    del _prompt_name
    with session_factory() as session:
        calls = ProviderCallRepository(session).for_project(project_id)[start - 1 : end]
        for item in calls:
            session.expunge(item)
        return calls


def _estimated_cost(session_factory: SessionFactory, project_id: int) -> Decimal:
    with session_factory() as session:
        values = session.scalars(
            select(ProviderCall.estimated_cost).where(ProviderCall.project_id == project_id)
        )
        return sum((item or Decimal("0") for item in values), Decimal("0"))
