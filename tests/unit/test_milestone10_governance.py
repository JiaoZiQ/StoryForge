"""Deterministic unit coverage for Milestone 10 provider governance."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, SecretStr, ValidationError
from sqlalchemy import Engine, select

from storyforge.database import create_session_factory
from storyforge.embeddings import MockEmbeddingProvider
from storyforge.embeddings.governed import GovernedEmbeddingProvider
from storyforge.enums import (
    BudgetPeriod,
    ModelProfile,
    PrivacyPolicy,
    ProviderCallStatus,
    TaskType,
    TokenUsageSource,
)
from storyforge.exceptions import (
    BudgetBlockedError,
    CircuitOpenError,
    ConfigurationError,
    PrivacyPolicyError,
    ProviderRateLimitError,
)
from storyforge.llm import MockFailure, MockLLMProvider
from storyforge.llm.exceptions import (
    LLMAuthenticationError,
    LLMContextLengthError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from storyforge.llm.types import (
    LLMMessage,
    LLMResponse,
    PromptReference,
    PromptRequest,
)
from storyforge.llm.types import (
    TokenUsage as ProviderTokenUsage,
)
from storyforge.models import ProjectBudget
from storyforge.privacy import ProviderDataPolicy, RedactionService
from storyforge.providers import (
    GovernedLLMProvider,
    ModelCapability,
    ModelReference,
    ModelRouter,
    ProviderCallContext,
    ProviderRegistry,
    build_provider_registry,
)
from storyforge.reliability import CircuitBreaker, ProviderRateLimiter, RetryPolicy
from storyforge.schemas.domain import ProjectCreate
from storyforge.services import ProjectService
from storyforge.settings import Settings
from storyforge.usage import BudgetService, PricingService, TokenUsage
from storyforge.usage.repositories import ProviderCallRepository


class _Result(BaseModel):
    ok: bool


class _ScriptedProvider:
    """Small network-free provider used to exercise exact gateway metadata."""

    provider_name = "scripted"

    def __init__(
        self,
        outcomes: list[BaseException | _Result],
        *,
        usage: ProviderTokenUsage | None = None,
    ) -> None:
        self._outcomes = outcomes
        self._usage = usage
        self.call_count = 0
        self.requests: list[PromptRequest] = []

    def generate(self, request: PromptRequest, response_model: type[BaseModel]) -> LLMResponse[Any]:
        self.requests.append(request)
        index = min(self.call_count, len(self._outcomes) - 1)
        self.call_count += 1
        outcome = self._outcomes[index]
        if isinstance(outcome, BaseException):
            raise outcome
        return LLMResponse(
            output=response_model.model_validate(outcome.model_dump()),
            provider=self.provider_name,
            model="scripted-v1",
            prompt=request.prompt,
            attempts=1,
            usage=self._usage,
        )


def _capability(**changes: object) -> ModelCapability:
    values: dict[str, object] = {
        "provider": "mock",
        "model": "mock-storyforge-v1",
        "model_type": "chat",
        "context_window": 1000,
        "max_output_tokens": 100,
        "supports_structured_output": True,
        "supports_json_schema": True,
        "input_cost_per_million": Decimal("1.25"),
        "output_cost_per_million": Decimal("2.50"),
        "cached_input_cost_per_million": Decimal("0.50"),
        "pricing_version": "2026-07",
        "pricing_effective_date": date(2026, 7, 1),
        "enabled": True,
        "external": False,
    }
    values.update(changes)
    return ModelCapability.model_validate(values)


def _request(label: str = "test") -> PromptRequest:
    return PromptRequest(
        prompt=PromptReference("provider.smoke", "v1"),
        messages=(LLMMessage("user", f"minimal {label}"),),
    )


def _governed(
    engine: Engine,
    project_id: int,
    primary: Any,
    fallback: Any,
    *,
    settings: Settings | None = None,
    retries: int = 0,
    clock: Any = None,
    sleeper: Any = None,
    deadline: float = 120,
    registry: ProviderRegistry | None = None,
    privacy_policy: PrivacyPolicy = PrivacyPolicy.OFFLINE,
    circuit: CircuitBreaker | None = None,
) -> GovernedLLMProvider:
    configured = settings or Settings()
    effective_registry = registry or build_provider_registry(configured)
    effective_clock = clock or (lambda: 0.0)
    return GovernedLLMProvider(
        session_factory=create_session_factory(engine),
        providers={
            ("mock", "mock-storyforge-v1"): primary,
            ("mock", "mock-storyforge-fallback-v1"): fallback,
        },
        registry=effective_registry,
        router=ModelRouter(effective_registry, configured),
        context=ProviderCallContext(
            project_id=project_id,
            privacy_policy=privacy_policy,
        ),
        budget=BudgetService(create_session_factory(engine), configured),
        rate_limiter=ProviderRateLimiter(
            requests_per_minute=100,
            tokens_per_minute=1_000_000,
            max_concurrency=2,
            clock=effective_clock,
        ),
        circuit_breaker=circuit
        or CircuitBreaker(
            failure_threshold=3,
            cooldown_seconds=30,
            clock=effective_clock,
        ),
        retry_policy=RetryPolicy(
            max_retries=retries,
            base_delay_seconds=2,
            jitter_ratio=0,
        ),
        sleeper=sleeper or (lambda _: None),
        clock=effective_clock,
        total_deadline_seconds=deadline,
    )


def test_registry_rejects_duplicates_disabled_and_unknown_models() -> None:
    capability = _capability()
    with pytest.raises(ConfigurationError, match="Duplicate"):
        ProviderRegistry([capability, capability])
    registry = ProviderRegistry([capability.model_copy(update={"enabled": False})])
    with pytest.raises(ConfigurationError, match="disabled"):
        registry.get(ModelReference(provider="mock", model="mock-storyforge-v1"))
    with pytest.raises(ConfigurationError, match="Unknown"):
        registry.get(ModelReference(provider="mock", model="missing"))


def test_registry_validates_capability_shapes_and_routes() -> None:
    with pytest.raises(ValidationError, match="Embedding models require"):
        _capability(model_type="embedding", supports_json_schema=False)
    with pytest.raises(ValidationError, match="Chat models cannot"):
        _capability(supports_embeddings=True, embedding_dimensions=64)
    with pytest.raises(ValidationError, match="version"):
        _capability(pricing_version=None)
    with pytest.raises(ValidationError, match="fallback loop"):
        from storyforge.providers.models import ModelRoute

        reference = ModelReference(provider="mock", model="mock-storyforge-v1")
        ModelRoute(
            task_type=TaskType.PLANNING,
            primary_model=reference,
            fallback_models=(reference,),
            max_input_tokens=100,
            max_output_tokens=10,
            timeout_seconds=1,
        )


def test_versioned_pricing_config_is_merged_without_guessing(tmp_path: Path) -> None:
    pricing = tmp_path / "pricing.json"
    pricing.write_text(
        json.dumps(
            {
                "prices": [
                    {
                        "provider": "mock",
                        "model": "mock-storyforge-v1",
                        "input_cost_per_million": "0.1",
                        "output_cost_per_million": "0.2",
                        "cached_input_cost_per_million": "0.05",
                        "currency": "USD",
                        "pricing_version": "test-v2",
                        "pricing_effective_date": "2026-07-17",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    registry = build_provider_registry(Settings(pricing_config_path=pricing))
    capability = registry.get(ModelReference(provider="mock", model="mock-storyforge-v1"))
    assert capability.input_cost_per_million == Decimal("0.1")
    assert capability.pricing_version == "test-v2"
    assert registry.get(
        ModelReference(provider="mock", model="mock-storyforge-fallback-v1")
    ).pricing_known

    pricing.write_text(
        json.dumps(
            {
                "prices": [
                    {
                        "provider": "unknown",
                        "model": "missing",
                        "input_cost_per_million": "1",
                        "pricing_version": "bad",
                        "pricing_effective_date": "2026-07-17",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="unknown model"):
        build_provider_registry(Settings(pricing_config_path=pricing))


def test_decimal_pricing_and_unknown_price_are_explicit() -> None:
    usage = TokenUsage(
        input_tokens=1000,
        output_tokens=200,
        cached_input_tokens=400,
        total_tokens=1200,
        source=TokenUsageSource.PROVIDER_REPORTED,
    )
    estimate = PricingService().estimate(_capability(), usage)
    assert estimate.amount == Decimal("0.00145000")
    assert estimate.snapshot.pricing_version == "2026-07"
    unknown = PricingService().estimate(
        _capability(
            input_cost_per_million=None,
            output_cost_per_million=None,
            cached_input_cost_per_million=None,
            pricing_version=None,
            pricing_effective_date=None,
        ),
        usage,
    )
    assert unknown.amount is None


@pytest.mark.parametrize(
    "values",
    [
        {"input_tokens": 1, "output_tokens": 1, "total_tokens": 1},
        {"input_tokens": 1, "output_tokens": 0, "cached_input_tokens": 2, "total_tokens": 1},
        {"input_tokens": -1, "output_tokens": 0, "total_tokens": -1},
    ],
)
def test_token_usage_rejects_inconsistent_or_negative_values(values: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        TokenUsage(source=TokenUsageSource.LOCAL_ESTIMATE, **values)


def test_redaction_and_privacy_never_retain_original_secrets() -> None:
    original = (
        "Authorization: Bearer secret-value "
        "api_key=sk-abcdefghijklmnop "
        "postgresql://writer:db-password@db/story"
    )
    rendered, summary = RedactionService().redact(original)
    assert "secret-value" not in rendered
    assert "sk-abcdefghijklmnop" not in rendered
    assert "db-password" not in rendered
    assert summary.total == 3

    request = PromptRequest(
        prompt=PromptReference("provider.smoke", "v1"),
        messages=(LLMMessage("user", original),),
    )
    prepared, decision = ProviderDataPolicy().prepare(
        request, policy=PrivacyPolicy.STRICT, external=True
    )
    assert decision.redactions.total == 3
    assert original not in prepared.messages[0].content
    with pytest.raises(PrivacyPolicyError):
        ProviderDataPolicy().prepare(request, policy=PrivacyPolicy.OFFLINE, external=True)


def test_retry_rate_limit_and_circuit_use_injected_time() -> None:
    retry = RetryPolicy(max_retries=2, base_delay_seconds=1, jitter_ratio=0)
    assert retry.retryable(LLMTimeoutError("timeout", attempts=1))
    assert not retry.retryable(LLMAuthenticationError("auth", attempts=1))
    assert retry.delay(2) == 4
    assert retry.delay(0, retry_after=3) == 3

    now = [0.0]
    limiter = ProviderRateLimiter(
        requests_per_minute=1,
        tokens_per_minute=10,
        max_concurrency=1,
        clock=lambda: now[0],
    )
    with limiter.acquire("one", estimated_tokens=5):
        with pytest.raises(ProviderRateLimitError, match="requests"):
            with limiter.acquire("one", estimated_tokens=1):
                pass
    now[0] = 61
    with limiter.acquire("one", estimated_tokens=10):
        pass

    circuit = CircuitBreaker(failure_threshold=2, cooldown_seconds=10, clock=lambda: now[0])
    circuit.record_failure("one")
    circuit.record_failure("one")
    assert circuit.snapshot("one").state.value == "open"
    with pytest.raises(CircuitOpenError):
        circuit.before_call("one")
    now[0] = 72
    circuit.before_call("one")
    assert circuit.snapshot("one").state.value == "half_open"
    circuit.record_success("one")
    assert circuit.snapshot("one").state.value == "closed"


def test_budget_reservation_warns_blocks_releases_and_rejects_unknown(db_engine: Engine) -> None:
    session_factory = create_session_factory(db_engine)
    project = ProjectService(session_factory).create(
        ProjectCreate(
            title="Budget",
            genre="test",
            premise="budget",
            target_chapters=1,
            target_words_per_chapter=100,
        )
    )
    settings = Settings(project_soft_budget=Decimal("1"), project_hard_budget=Decimal("2"))
    service = BudgetService(session_factory, settings)
    assert service.reserve(project.id, Decimal("1.5")).warning
    with pytest.raises(BudgetBlockedError):
        service.reserve(project.id, Decimal("0.6"))
    service.release(project.id, Decimal("1.5"))
    with pytest.raises(BudgetBlockedError, match="Unknown"):
        service.reserve(project.id, None)


def test_gateway_retries_falls_back_audits_and_reuses_in_memory(db_engine: Engine) -> None:
    session_factory = create_session_factory(db_engine)
    project = ProjectService(session_factory).create(
        ProjectCreate(
            title="Gateway",
            genre="test",
            premise="gateway",
            target_chapters=1,
            target_words_per_chapter=100,
        )
    )
    settings = Settings()
    registry = build_provider_registry(settings)
    primary = MockLLMProvider({_Result: _Result(ok=True)}, failures=(MockFailure.TIMEOUT,))
    fallback = MockLLMProvider({_Result: _Result(ok=True)})
    gateway = GovernedLLMProvider(
        session_factory=session_factory,
        providers={
            ("mock", "mock-storyforge-v1"): primary,
            ("mock", "mock-storyforge-fallback-v1"): fallback,
        },
        registry=registry,
        router=ModelRouter(registry, settings),
        context=ProviderCallContext(project_id=project.id),
        budget=BudgetService(session_factory, settings),
        rate_limiter=ProviderRateLimiter(
            requests_per_minute=100, tokens_per_minute=1_000_000, max_concurrency=2
        ),
        circuit_breaker=CircuitBreaker(failure_threshold=3, cooldown_seconds=30),
        retry_policy=RetryPolicy(max_retries=0),
        sleeper=lambda _: None,
    )
    response = gateway.generate(_request("fallback"), _Result)
    assert response.output.ok
    assert primary.call_count == 1
    assert fallback.call_count == 1
    with session_factory() as session:
        calls = ProviderCallRepository(session).for_project(project.id)
        assert [item.status.value for item in calls] == ["timed_out", "succeeded"]
        assert calls[-1].fallback_index == 1
        assert all(not hasattr(item, "prompt") for item in calls)
    gateway.generate(_request("fallback"), _Result)
    assert primary.call_count == 1
    assert fallback.call_count == 1


def test_embedding_gateway_redacts_audits_usage_and_blocks_offline(db_engine: Engine) -> None:
    session_factory = create_session_factory(db_engine)
    project = ProjectService(session_factory).create(
        ProjectCreate(
            title="Embedding governance",
            genre="test",
            premise="safe vectors",
            target_chapters=1,
            target_words_per_chapter=100,
        )
    )
    settings = Settings()
    capability = ModelCapability(
        provider="external",
        model="embedding-test-v1",
        model_type="embedding",
        context_window=8_192,
        max_output_tokens=0,
        supports_batch=True,
        supports_embeddings=True,
        embedding_dimensions=64,
        input_cost_per_million=Decimal("0"),
        output_cost_per_million=Decimal("0"),
        pricing_version="test-v1",
        pricing_effective_date=date(2026, 7, 17),
        external=True,
    )

    def governed(policy: PrivacyPolicy) -> GovernedEmbeddingProvider:
        return GovernedEmbeddingProvider(
            provider=MockEmbeddingProvider(dimensions=64),
            capability=capability,
            task_type=TaskType.EMBEDDING_QUERY,
            session_factory=session_factory,
            context=ProviderCallContext(project_id=project.id, privacy_policy=policy),
            budget=BudgetService(session_factory, settings),
            rate_limiter=ProviderRateLimiter(
                requests_per_minute=100,
                tokens_per_minute=1_000_000,
                max_concurrency=2,
            ),
            circuit_breaker=CircuitBreaker(failure_threshold=2, cooldown_seconds=30),
            max_retries=0,
            sleeper=lambda _: None,
        )

    vector = governed(PrivacyPolicy.STRICT).embed_query("api_key=sk-abcdefghijklmnop")
    assert len(vector) == 64
    with pytest.raises(PrivacyPolicyError):
        governed(PrivacyPolicy.OFFLINE).embed_query("future chapter body")
    with session_factory() as session:
        calls = ProviderCallRepository(session).for_project(project.id)
        assert [item.status.value for item in calls] == ["succeeded", "failed"]
        assert calls[0].task_type is TaskType.EMBEDDING_QUERY
        assert calls[0].usage_source is TokenUsageSource.LOCAL_ESTIMATE
        assert calls[0].total_tokens > 0
        assert all(not hasattr(item, "embedding") for item in calls)


def test_all_profiles_route_deterministically_and_reject_incompatible_models() -> None:
    external = Settings(
        llm_provider="openai-compatible",
        llm_model="external-structured-v1",
        llm_api_key=SecretStr("unit-test-placeholder"),
        mock_mode=False,
        model_profile=ModelProfile.BALANCED,
        privacy_policy=PrivacyPolicy.STRICT,
    )
    registry = build_provider_registry(external)
    router = ModelRouter(registry, external)
    assert router.route(TaskType.PLANNING, ModelProfile.OFFLINE).primary_model == ModelReference(
        provider="mock", model="mock-storyforge-v1"
    )
    for profile in (ModelProfile.ECONOMY, ModelProfile.BALANCED, ModelProfile.QUALITY):
        route = router.route(TaskType.CHAPTER_DRAFTING, profile)
        assert route.primary_model == ModelReference(
            provider="openai-compatible", model="external-structured-v1"
        )

    bad_fallback = _capability(
        model="mock-storyforge-fallback-v1",
        supports_structured_output=False,
        supports_json_schema=False,
    )
    incompatible_chat = ProviderRegistry([_capability(), bad_fallback])
    with pytest.raises(ConfigurationError, match="Fallback chat model"):
        ModelRouter(incompatible_chat, Settings()).route(TaskType.PLANNING, ModelProfile.OFFLINE)

    wrong_dimensions = ModelCapability(
        provider="mock",
        model="mock-hash-embedding-v1",
        model_type="embedding",
        context_window=8_192,
        max_output_tokens=0,
        supports_batch=True,
        supports_embeddings=True,
        embedding_dimensions=32,
        enabled=True,
        external=False,
    )
    with pytest.raises(ConfigurationError, match="dimensions"):
        ModelRouter(ProviderRegistry([wrong_dimensions]), Settings()).route(
            TaskType.EMBEDDING_QUERY, ModelProfile.OFFLINE
        )


def test_retry_after_authentication_and_total_deadline_are_exact(db_engine: Engine) -> None:
    session_factory = create_session_factory(db_engine)
    project = ProjectService(session_factory).create(
        ProjectCreate(
            title="Reliability semantics",
            genre="test",
            premise="bounded retries",
            target_chapters=1,
            target_words_per_chapter=100,
        )
    )
    now = [0.0]
    sleeps: list[float] = []

    def clock() -> float:
        return now[0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    retrying = _ScriptedProvider(
        [
            LLMRateLimitError("rate limited", attempts=1, status_code=429, retry_after=3),
            _Result(ok=True),
        ]
    )
    unused_fallback = _ScriptedProvider([_Result(ok=True)])
    response = _governed(
        db_engine,
        project.id,
        retrying,
        unused_fallback,
        retries=1,
        clock=clock,
        sleeper=sleep,
        deadline=10,
    ).generate(_request("retry-after"), _Result)
    assert response.output.ok
    assert retrying.call_count == 2
    assert unused_fallback.call_count == 0
    assert sleeps == [3]

    auth = _ScriptedProvider([LLMAuthenticationError("invalid", attempts=1)])
    auth_fallback = _ScriptedProvider([_Result(ok=True)])
    with pytest.raises(LLMAuthenticationError):
        _governed(
            db_engine,
            project.id,
            auth,
            auth_fallback,
            retries=2,
            clock=clock,
            sleeper=sleep,
        ).generate(_request("auth"), _Result)
    assert auth.call_count == 1
    assert auth_fallback.call_count == 0

    deadline_primary = _ScriptedProvider([LLMTimeoutError("slow", attempts=1)])
    deadline_fallback = _ScriptedProvider([_Result(ok=True)])
    with pytest.raises(LLMTimeoutError, match="deadline"):
        _governed(
            db_engine,
            project.id,
            deadline_primary,
            deadline_fallback,
            retries=1,
            clock=clock,
            sleeper=sleep,
            deadline=1,
        ).generate(_request("deadline"), _Result)
    assert deadline_primary.call_count == 1
    assert deadline_fallback.call_count == 0


def test_context_length_routes_to_registered_long_context_fallback(db_engine: Engine) -> None:
    session_factory = create_session_factory(db_engine)
    project = ProjectService(session_factory).create(
        ProjectCreate(
            title="Long context",
            genre="test",
            premise="route long input",
            target_chapters=1,
            target_words_per_chapter=100,
        )
    )
    primary = MockLLMProvider({_Result: _Result(ok=True)}, failures=(MockFailure.CONTEXT_LENGTH,))
    fallback = MockLLMProvider({_Result: _Result(ok=True)})
    response = _governed(db_engine, project.id, primary, fallback).generate(
        _request("context-length"), _Result
    )
    assert response.output.ok
    assert primary.call_count == 1
    assert fallback.call_count == 1
    assert response.model == "mock-storyforge-fallback-v1"
    assert not RetryPolicy(max_retries=2).retryable(LLMContextLengthError("too long", attempts=1))
    registry = build_provider_registry(Settings())
    primary_capability = registry.get(ModelReference(provider="mock", model="mock-storyforge-v1"))
    fallback_capability = registry.get(
        ModelReference(provider="mock", model="mock-storyforge-fallback-v1")
    )
    assert fallback_capability.context_window > primary_capability.context_window


def test_usage_sources_cover_provider_estimate_mock_and_unknown(db_engine: Engine) -> None:
    session_factory = create_session_factory(db_engine)
    project = ProjectService(session_factory).create(
        ProjectCreate(
            title="Usage provenance",
            genre="test",
            premise="four explicit sources",
            target_chapters=1,
            target_words_per_chapter=100,
        )
    )
    reported_usage = ProviderTokenUsage(
        input_tokens=3,
        output_tokens=2,
        total_tokens=5,
        source=TokenUsageSource.PROVIDER_REPORTED,
    )
    calls = (
        (
            "provider-reported",
            _ScriptedProvider([_Result(ok=True)], usage=reported_usage),
            TokenUsageSource.PROVIDER_REPORTED,
        ),
        ("local-estimate", _ScriptedProvider([_Result(ok=True)]), TokenUsageSource.LOCAL_ESTIMATE),
        ("mock", MockLLMProvider({_Result: _Result(ok=True)}), TokenUsageSource.MOCK),
    )
    for label, provider, _expected in calls:
        _governed(
            db_engine,
            project.id,
            provider,
            _ScriptedProvider([_Result(ok=True)]),
        ).generate(_request(label), _Result)
    with pytest.raises(LLMAuthenticationError):
        _governed(
            db_engine,
            project.id,
            _ScriptedProvider([LLMAuthenticationError("invalid", attempts=1)]),
            _ScriptedProvider([_Result(ok=True)]),
        ).generate(_request("unknown"), _Result)
    with session_factory() as session:
        persisted = ProviderCallRepository(session).for_project(project.id)
        assert [item.usage_source for item in persisted] == [
            TokenUsageSource.PROVIDER_REPORTED,
            TokenUsageSource.LOCAL_ESTIMATE,
            TokenUsageSource.MOCK,
            TokenUsageSource.UNKNOWN,
        ]
        assert persisted[-1].status is ProviderCallStatus.FAILED


def test_estimated_and_billed_budget_costs_remain_distinct_decimals(db_engine: Engine) -> None:
    session_factory = create_session_factory(db_engine)
    project = ProjectService(session_factory).create(
        ProjectCreate(
            title="Decimal settlement",
            genre="test",
            premise="separate estimated and billed values",
            target_chapters=1,
            target_words_per_chapter=100,
        )
    )
    budget = BudgetService(session_factory, Settings())
    reservation = budget.reserve(project.id, Decimal("0.75000000"))
    budget.settle(
        project.id,
        reserved=reservation.reserved_amount,
        estimated_cost=Decimal("0.70000000"),
        billed_cost=Decimal("0.61000000"),
    )
    with session_factory() as session:
        persisted = session.scalar(
            select(ProjectBudget).where(ProjectBudget.project_id == project.id)
        )
        assert persisted is not None
        assert isinstance(persisted.spent_estimated, Decimal)
        assert isinstance(persisted.spent_billed, Decimal)
        assert persisted.spent_estimated == Decimal("0.70000000")
        assert persisted.spent_billed == Decimal("0.61000000")
        assert persisted.reserved_estimated == Decimal("0")


def test_fallback_rechecks_privacy_budget_and_circuit(db_engine: Engine) -> None:
    session_factory = create_session_factory(db_engine)
    project = ProjectService(session_factory).create(
        ProjectCreate(
            title="Fallback governance",
            genre="test",
            premise="every candidate is checked again",
            target_chapters=1,
            target_words_per_chapter=100,
        )
    )
    configured = Settings()
    capabilities = build_provider_registry(configured).list()

    external_fallback_registry = ProviderRegistry(
        [
            item.model_copy(update={"external": True})
            if item.key == ("mock", "mock-storyforge-fallback-v1")
            else item
            for item in capabilities
        ]
    )
    privacy_primary = _ScriptedProvider([LLMTimeoutError("timeout", attempts=1)])
    privacy_fallback = _ScriptedProvider([_Result(ok=True)])
    with pytest.raises(PrivacyPolicyError):
        _governed(
            db_engine,
            project.id,
            privacy_primary,
            privacy_fallback,
            registry=external_fallback_registry,
            privacy_policy=PrivacyPolicy.OFFLINE,
        ).generate(_request("privacy-fallback"), _Result)
    assert privacy_primary.call_count == 1
    assert privacy_fallback.call_count == 0

    expensive_fallback_registry = ProviderRegistry(
        [
            item.model_copy(
                update={
                    "input_cost_per_million": Decimal("100000"),
                    "output_cost_per_million": Decimal("100000"),
                }
            )
            if item.key == ("mock", "mock-storyforge-fallback-v1")
            else item
            for item in capabilities
        ]
    )
    BudgetService(session_factory, configured).set(
        project.id,
        soft_limit=Decimal("5"),
        hard_limit=Decimal("10"),
        currency="USD",
        period=BudgetPeriod.LIFETIME,
        enabled=True,
    )
    budget_primary = _ScriptedProvider([LLMTimeoutError("timeout", attempts=1)])
    budget_fallback = _ScriptedProvider([_Result(ok=True)])
    with pytest.raises(BudgetBlockedError):
        _governed(
            db_engine,
            project.id,
            budget_primary,
            budget_fallback,
            registry=expensive_fallback_registry,
        ).generate(_request("budget-fallback"), _Result)
    assert budget_primary.call_count == 1
    assert budget_fallback.call_count == 0

    now = [0.0]
    circuit = CircuitBreaker(
        failure_threshold=1,
        cooldown_seconds=30,
        clock=lambda: now[0],
    )
    circuit.record_failure("mock/mock-storyforge-v1")
    circuit_primary = _ScriptedProvider([_Result(ok=True)])
    circuit_fallback = _ScriptedProvider([_Result(ok=True)])
    response = _governed(
        db_engine,
        project.id,
        circuit_primary,
        circuit_fallback,
        clock=lambda: now[0],
        circuit=circuit,
    ).generate(_request("circuit-fallback"), _Result)
    assert response.output.ok
    assert circuit_primary.call_count == 0
    assert circuit_fallback.call_count == 1


def test_agents_depend_only_on_llm_boundary_and_factory_wraps_raw_providers() -> None:
    root = Path(__file__).resolve().parents[2]
    agent_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in (root / "src/storyforge/agents").glob("*.py")
    )
    for forbidden in ("import openai", "import httpx", "GovernedLLMProvider"):
        assert forbidden not in agent_sources
    assert "LLMProvider" in agent_sources
    factory = (root / "src/storyforge/application/factory.py").read_text(encoding="utf-8")
    assert "provider = GovernedLLMProvider(" in factory
    assert "yield provider" in factory
