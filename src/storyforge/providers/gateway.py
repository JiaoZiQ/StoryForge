"""Unified governed LLM entry used by every existing structured Agent."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import select

from storyforge.database import SessionFactory
from storyforge.enums import (
    ModelProfile,
    PrivacyPolicy,
    ProviderCallStatus,
    TokenUsageSource,
    WorkflowRunStatus,
)
from storyforge.exceptions import (
    BudgetBlockedError,
    CircuitOpenError,
    IdempotencyConflictError,
    PrivacyPolicyError,
    ProviderRateLimitError,
)
from storyforge.llm import LLMProvider
from storyforge.llm.exceptions import (
    LLMAuthenticationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMServiceError,
    LLMTimeoutError,
)
from storyforge.llm.types import LLMResponse, PromptRequest, ResponseT
from storyforge.models import ProviderCall, WorkflowRun
from storyforge.models.base import utc_now
from storyforge.privacy import ProviderDataPolicy
from storyforge.providers.models import ModelReference
from storyforge.providers.registry import ProviderRegistry
from storyforge.providers.routing import ModelRouter, task_for_prompt
from storyforge.reliability import (
    CircuitBreaker,
    IdempotencyService,
    ProviderRateLimiter,
    RetryPolicy,
)
from storyforge.usage import BudgetService, PricingService
from storyforge.usage.models import TokenUsage
from storyforge.usage.repositories import ProviderCallRepository


@dataclass(frozen=True, slots=True)
class ProviderCallContext:
    """Small business identifiers; never contains prompt text or credentials."""

    project_id: int | None = None
    workflow_run_id: int | None = None
    chapter_id: int | None = None
    chapter_version_id: int | None = None
    idempotency_scope: str | None = None
    profile: ModelProfile = ModelProfile.OFFLINE
    privacy_policy: PrivacyPolicy = PrivacyPolicy.OFFLINE


class GovernedLLMProvider:
    """Apply routing, policy, budget, reliability, idempotency, and audit in order."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        providers: Mapping[tuple[str, str], LLMProvider],
        registry: ProviderRegistry,
        router: ModelRouter,
        context: ProviderCallContext,
        budget: BudgetService,
        rate_limiter: ProviderRateLimiter,
        circuit_breaker: CircuitBreaker,
        retry_policy: RetryPolicy,
        privacy: ProviderDataPolicy | None = None,
        pricing: PricingService | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        total_deadline_seconds: float = 120.0,
    ) -> None:
        self._session_factory = session_factory
        self._providers = dict(providers)
        self._registry = registry
        self._router = router
        self._context = context
        self._budget = budget
        self._limiter = rate_limiter
        self._circuit = circuit_breaker
        self._retry = retry_policy
        self._privacy = privacy or ProviderDataPolicy()
        self._pricing = pricing or PricingService()
        self._sleeper = sleeper
        self._clock = clock
        self._deadline = total_deadline_seconds
        self._idempotency = IdempotencyService(session_factory)
        self._cache: dict[str, LLMResponse[BaseModel]] = {}

    @property
    def provider_name(self) -> str:
        route = self._router.route(task_for_prompt("provider.smoke"), self._context.profile)
        return route.primary_model.provider

    def generate(
        self,
        request: PromptRequest,
        response_model: type[ResponseT],
    ) -> LLMResponse[ResponseT]:
        task_type = task_for_prompt(request.prompt.name)
        route = self._router.route(task_type, self._context.profile)
        request_hash = self._request_hash(request)
        workflow_run_id = self._effective_workflow_run_id()
        idempotency_key = self._idempotency_key(request_hash, task_type.value, workflow_run_id)
        cached = self._cache.get(idempotency_key)
        if cached is not None:
            return LLMResponse(
                output=response_model.model_validate(cached.output.model_dump()),
                provider=cached.provider,
                model=cached.model,
                prompt=request.prompt,
                attempts=cached.attempts,
                usage=cached.usage,
                request_id=cached.request_id,
            )
        claim = self._idempotency.claim(idempotency_key)
        if claim.replay:
            raise IdempotencyConflictError(
                "Completed provider result must be reused through its persisted domain artifact"
            )

        started = self._clock()
        candidates = (route.primary_model, *route.fallback_models)
        last_error: Exception | None = None
        global_attempt = 0
        for fallback_index, reference in enumerate(candidates):
            capability = self._registry.get(reference)
            provider = self._providers.get(reference.key)
            if provider is None:
                last_error = LLMServiceError(
                    "Registered provider runtime is unavailable", attempts=max(1, global_attempt)
                )
                continue
            try:
                prepared, _decision = self._privacy.prepare(
                    request,
                    policy=self._context.privacy_policy,
                    external=capability.external,
                )
                input_text = "\n".join(message.content for message in prepared.messages)
                preflight_usage = self._pricing.local_usage(input_text)
                preflight_usage = TokenUsage(
                    input_tokens=preflight_usage.input_tokens,
                    output_tokens=route.max_output_tokens,
                    total_tokens=preflight_usage.input_tokens + route.max_output_tokens,
                    source=TokenUsageSource.LOCAL_ESTIMATE,
                )
                preflight_price = self._pricing.estimate(capability, preflight_usage)
            except Exception as exc:
                global_attempt += 1
                privacy_call_id = self._start_call(
                    request=request,
                    request_hash=request_hash,
                    idempotency_key=idempotency_key,
                    reference=reference,
                    attempt=global_attempt,
                    fallback_index=fallback_index,
                    workflow_run_id=workflow_run_id,
                    pricing_snapshot={},
                )
                self._finish_call(
                    privacy_call_id,
                    status=self._status_for_error(exc),
                    usage=None,
                    estimated_cost=None,
                    latency_ms=0,
                    request_id=None,
                    error_code=type(exc).__name__,
                )
                last_error = exc
                break

            for retry_index in range(self._retry.max_retries + 1):
                global_attempt += 1
                if self._clock() - started >= self._deadline:
                    last_error = LLMTimeoutError(
                        "Provider total deadline was exhausted", attempts=global_attempt
                    )
                    break
                call_id: int | None = None
                reserved = Decimal("0")
                try:
                    circuit_key = f"{reference.provider}/{reference.model}"
                    self._circuit.before_call(circuit_key)
                    self._budget.check_workflow(
                        workflow_run_id,
                        estimated_cost=preflight_price.amount,
                        estimated_tokens=preflight_usage.total_tokens,
                    )
                    if self._context.project_id is not None:
                        decision = self._budget.reserve(
                            self._context.project_id, preflight_price.amount
                        )
                        reserved = decision.reserved_amount
                    call_id = self._start_call(
                        request=request,
                        request_hash=request_hash,
                        idempotency_key=idempotency_key,
                        reference=reference,
                        attempt=global_attempt,
                        fallback_index=fallback_index,
                        workflow_run_id=workflow_run_id,
                        pricing_snapshot=preflight_price.snapshot.model_dump(mode="json"),
                    )
                    call_started = self._clock()
                    with self._limiter.acquire(
                        circuit_key, estimated_tokens=preflight_usage.total_tokens
                    ):
                        response = provider.generate(prepared, response_model)
                    latency_ms = max(0, round((self._clock() - call_started) * 1000))
                    usage = self._normalize_usage(response, input_text)
                    price = self._pricing.estimate(capability, usage)
                    finished_call_id = self._finish_call(
                        call_id,
                        status=ProviderCallStatus.SUCCEEDED,
                        usage=usage,
                        estimated_cost=price.amount,
                        latency_ms=latency_ms,
                        request_id=response.request_id,
                    )
                    if self._context.project_id is not None:
                        self._budget.settle(
                            self._context.project_id,
                            reserved=reserved,
                            estimated_cost=price.amount,
                        )
                    self._circuit.record_success(circuit_key)
                    response_hash = hashlib.sha256(
                        response.output.model_dump_json().encode("utf-8")
                    ).hexdigest()
                    self._idempotency.succeed(idempotency_key, finished_call_id, response_hash)
                    governed = LLMResponse(
                        output=response.output,
                        provider=reference.provider,
                        model=reference.model,
                        prompt=response.prompt,
                        attempts=global_attempt,
                        usage=response.usage,
                        request_id=response.request_id,
                    )
                    self._cache[idempotency_key] = governed
                    return governed
                except Exception as exc:
                    last_error = exc
                    if self._context.project_id is not None and reserved:
                        self._budget.release(self._context.project_id, reserved)
                    status = self._status_for_error(exc)
                    if call_id is None:
                        call_id = self._start_call(
                            request=request,
                            request_hash=request_hash,
                            idempotency_key=idempotency_key,
                            reference=reference,
                            attempt=global_attempt,
                            fallback_index=fallback_index,
                            workflow_run_id=workflow_run_id,
                            pricing_snapshot=preflight_price.snapshot.model_dump(mode="json"),
                        )
                    self._finish_call(
                        call_id,
                        status=status,
                        usage=None,
                        estimated_cost=None,
                        latency_ms=0,
                        request_id=None,
                        error_code=type(exc).__name__,
                    )
                    if isinstance(exc, (LLMTimeoutError, LLMServiceError)):
                        self._circuit.record_failure(circuit_key)
                    if not self._retry.retryable(exc) or retry_index >= self._retry.max_retries:
                        break
                    self._sleeper(
                        self._retry.delay(
                            retry_index,
                            getattr(exc, "retry_after", None),
                        )
                    )
            if isinstance(last_error, (LLMAuthenticationError, LLMRefusalError)):
                break
            if isinstance(last_error, (BudgetBlockedError, PrivacyPolicyError)):
                break

        error_code = type(last_error).__name__ if last_error is not None else "provider_failed"
        self._idempotency.fail(idempotency_key, error_code)
        if isinstance(last_error, Exception):
            raise last_error
        raise LLMProviderError("All registered providers failed", attempts=max(1, global_attempt))

    def _start_call(
        self,
        *,
        request: PromptRequest,
        request_hash: str,
        idempotency_key: str,
        reference: ModelReference,
        attempt: int,
        fallback_index: int,
        workflow_run_id: int | None,
        pricing_snapshot: dict[str, object],
    ) -> int:
        with self._session_factory.begin() as session:
            row = ProviderCallRepository(session).add(
                ProviderCall(
                    project_id=self._context.project_id,
                    workflow_run_id=workflow_run_id,
                    chapter_id=self._context.chapter_id,
                    chapter_version_id=self._context.chapter_version_id,
                    task_type=task_for_prompt(request.prompt.name),
                    provider=reference.provider,
                    model=reference.model,
                    profile=self._context.profile,
                    privacy_policy=self._context.privacy_policy,
                    prompt_name=request.prompt.name,
                    prompt_version=request.prompt.version,
                    request_hash=request_hash,
                    idempotency_key=idempotency_key,
                    status=ProviderCallStatus.RUNNING,
                    attempt=attempt,
                    fallback_index=fallback_index,
                    fallback_reason=("primary_failure" if fallback_index else None),
                    pricing_snapshot=pricing_snapshot,
                    currency=str(pricing_snapshot.get("currency", "USD")),
                )
            )
            return row.id

    def _finish_call(
        self,
        call_id: int,
        *,
        status: ProviderCallStatus,
        usage: TokenUsage | None,
        estimated_cost: Decimal | None,
        latency_ms: int,
        request_id: str | None,
        error_code: str | None = None,
    ) -> int:
        with self._session_factory.begin() as session:
            repository = ProviderCallRepository(session)
            row = repository.get(call_id)
            if row is None:
                raise RuntimeError("Provider call audit row disappeared")
            changes: dict[str, object] = {
                "status": status,
                "latency_ms": latency_ms,
                "provider_request_id": request_id,
                "error_code": error_code,
                "completed_at": utc_now(),
            }
            if usage is not None:
                changes.update(
                    {
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "cached_input_tokens": usage.cached_input_tokens,
                        "total_tokens": usage.total_tokens,
                        "usage_source": usage.source,
                        "estimated_cost": estimated_cost,
                    }
                )
            repository.update(row, changes)
            if row.workflow_run_id is not None:
                workflow = session.get(WorkflowRun, row.workflow_run_id)
                if workflow is not None:
                    workflow.provider_call_count += 1
                    workflow.provider_input_tokens += usage.input_tokens if usage else 0
                    workflow.provider_output_tokens += usage.output_tokens if usage else 0
                    workflow.provider_estimated_cost += estimated_cost or Decimal("0")
                    workflow.provider_fallback_count += int(row.fallback_index > 0)
                    workflow.provider_rate_limit_count += int(
                        status is ProviderCallStatus.RATE_LIMITED
                    )
            return row.id

    @staticmethod
    def _normalize_usage(response: LLMResponse[ResponseT], input_text: str) -> TokenUsage:
        if response.usage is not None:
            return TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cached_input_tokens=response.usage.cached_input_tokens,
                total_tokens=response.usage.total_tokens,
                source=response.usage.source,
            )
        output_text = response.output.model_dump_json()
        return PricingService.local_usage(input_text, output_text)

    def _idempotency_key(
        self, request_hash: str, task_type: str, workflow_run_id: int | None
    ) -> str:
        payload = {
            "project": self._context.project_id,
            "workflow": workflow_run_id,
            "chapter": self._context.chapter_id,
            "version": self._context.chapter_version_id,
            "scope": self._context.idempotency_scope,
            "task": task_type,
            "profile": self._context.profile.value,
            "request_hash": request_hash,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _effective_workflow_run_id(self) -> int | None:
        if self._context.workflow_run_id is not None:
            return self._context.workflow_run_id
        if self._context.project_id is None or self._context.chapter_id is None:
            return None
        with self._session_factory() as session:
            return session.scalar(
                select(WorkflowRun.id)
                .where(
                    WorkflowRun.project_id == self._context.project_id,
                    WorkflowRun.chapter_id == self._context.chapter_id,
                    WorkflowRun.status.in_(
                        (
                            WorkflowRunStatus.PENDING,
                            WorkflowRunStatus.RUNNING,
                            WorkflowRunStatus.PAUSED,
                        )
                    ),
                )
                .order_by(WorkflowRun.id.desc())
                .limit(1)
            )

    @staticmethod
    def _request_hash(request: PromptRequest) -> str:
        payload = {
            "prompt": request.prompt.name,
            "version": request.prompt.version,
            "messages": [
                {"role": message.role, "content": message.content} for message in request.messages
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()

    @staticmethod
    def _status_for_error(error: BaseException) -> ProviderCallStatus:
        if isinstance(error, BudgetBlockedError):
            return ProviderCallStatus.BUDGET_BLOCKED
        if isinstance(error, (ProviderRateLimitError, LLMRateLimitError)):
            return ProviderCallStatus.RATE_LIMITED
        if isinstance(error, LLMTimeoutError):
            return ProviderCallStatus.TIMED_OUT
        if isinstance(error, CircuitOpenError):
            return ProviderCallStatus.CIRCUIT_OPEN
        return ProviderCallStatus.FAILED
