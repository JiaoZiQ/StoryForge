"""Governed embedding boundary with content-free usage audit."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from storyforge.database import SessionFactory
from storyforge.embeddings.base import (
    EmbeddingDimensionError,
    EmbeddingInvalidResponseError,
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingTimeoutError,
)
from storyforge.enums import (
    PrivacyPolicy,
    ProviderCallStatus,
    TaskType,
    TokenUsageSource,
    WorkflowRunStatus,
)
from storyforge.exceptions import (
    BudgetBlockedError,
    CircuitOpenError,
    PrivacyPolicyError,
    ProviderRateLimitError,
)
from storyforge.models import ProviderCall, WorkflowRun
from storyforge.models.base import utc_now
from storyforge.privacy import RedactionService
from storyforge.providers.gateway import ProviderCallContext
from storyforge.providers.models import ModelCapability
from storyforge.reliability import CircuitBreaker, ProviderRateLimiter
from storyforge.usage import BudgetService, PricingService
from storyforge.usage.models import TokenUsage
from storyforge.usage.repositories import ProviderCallRepository


class GovernedEmbeddingProvider:
    """Apply egress, budget, reliability, and audit controls to embeddings."""

    def __init__(
        self,
        *,
        provider: EmbeddingProvider,
        capability: ModelCapability,
        task_type: TaskType,
        session_factory: SessionFactory,
        context: ProviderCallContext,
        budget: BudgetService,
        rate_limiter: ProviderRateLimiter,
        circuit_breaker: CircuitBreaker,
        max_retries: int,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if task_type not in {TaskType.EMBEDDING_DOCUMENT, TaskType.EMBEDDING_QUERY}:
            raise ValueError("Governed embedding task type is invalid")
        self._provider = provider
        self._capability = capability
        self._task_type = task_type
        self._session_factory = session_factory
        self._context = context
        self._budget = budget
        self._limiter = rate_limiter
        self._circuit = circuit_breaker
        self._max_retries = max_retries
        self._sleeper = sleeper
        self._clock = clock
        self._pricing = PricingService()
        self._redactor = RedactionService()

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def model_name(self) -> str:
        return self._provider.model_name

    @property
    def dimensions(self) -> int:
        return self._provider.dimensions

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        workflow_run_id = self._effective_workflow_run_id()
        request_hash = self._hash(texts)
        try:
            prepared = self._prepare(texts)
        except Exception as exc:
            privacy_call_id = self._start_call(
                request_hash=request_hash,
                workflow_run_id=workflow_run_id,
                attempt=1,
                pricing_snapshot={},
            )
            self._finish_call(
                privacy_call_id,
                status=self._status_for_error(exc),
                usage=None,
                estimated_cost=None,
                latency_ms=0,
                workflow_run_id=workflow_run_id,
                error_code=type(exc).__name__,
            )
            raise
        request_hash = self._hash(prepared)
        usage = self._pricing.local_usage("\n".join(prepared))
        usage = TokenUsage(
            input_tokens=usage.input_tokens,
            output_tokens=0,
            total_tokens=usage.input_tokens,
            source=(
                TokenUsageSource.MOCK
                if self._capability.provider == "mock"
                else TokenUsageSource.LOCAL_ESTIMATE
            ),
        )
        price = self._pricing.estimate(self._capability, usage)
        circuit_key = f"{self._capability.provider}/{self._capability.model}"
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 2):
            reserved = Decimal("0")
            call_id: int | None = None
            started = self._clock()
            try:
                self._circuit.before_call(circuit_key)
                self._budget.check_workflow(
                    workflow_run_id,
                    estimated_cost=price.amount,
                    estimated_tokens=usage.total_tokens,
                )
                if self._context.project_id is not None:
                    reserved = self._budget.reserve(
                        self._context.project_id, price.amount
                    ).reserved_amount
                call_id = self._start_call(
                    request_hash=request_hash,
                    workflow_run_id=workflow_run_id,
                    attempt=attempt,
                    pricing_snapshot=price.snapshot.model_dump(mode="json"),
                )
                with self._limiter.acquire(circuit_key, estimated_tokens=usage.total_tokens):
                    vectors = self._provider.embed_texts(prepared)
                if len(vectors) != len(prepared) or any(
                    len(vector) != self.dimensions for vector in vectors
                ):
                    raise EmbeddingDimensionError("Embedding response shape is invalid")
                latency = max(0, round((self._clock() - started) * 1000))
                self._finish_call(
                    call_id,
                    status=ProviderCallStatus.SUCCEEDED,
                    usage=usage,
                    estimated_cost=price.amount,
                    latency_ms=latency,
                    workflow_run_id=workflow_run_id,
                )
                if self._context.project_id is not None:
                    self._budget.settle(
                        self._context.project_id,
                        reserved=reserved,
                        estimated_cost=price.amount,
                    )
                self._circuit.record_success(circuit_key)
                return vectors
            except Exception as exc:
                last_error = exc
                if self._context.project_id is not None and reserved:
                    self._budget.release(self._context.project_id, reserved)
                if call_id is None:
                    call_id = self._start_call(
                        request_hash=request_hash,
                        workflow_run_id=workflow_run_id,
                        attempt=attempt,
                        pricing_snapshot=price.snapshot.model_dump(mode="json"),
                    )
                self._finish_call(
                    call_id,
                    status=self._status_for_error(exc),
                    usage=None,
                    estimated_cost=None,
                    latency_ms=max(0, round((self._clock() - started) * 1000)),
                    workflow_run_id=workflow_run_id,
                    error_code=type(exc).__name__,
                )
                if isinstance(exc, (EmbeddingTimeoutError, EmbeddingProviderError)):
                    self._circuit.record_failure(circuit_key)
                if not self._retryable(exc) or attempt > self._max_retries:
                    break
                self._sleeper(min(2.0, 0.25 * (2 ** (attempt - 1))))
        if last_error is not None:
            raise last_error
        raise EmbeddingProviderError("Embedding provider failed")

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def _prepare(self, texts: Sequence[str]) -> list[str]:
        if self._context.privacy_policy is PrivacyPolicy.OFFLINE and self._capability.external:
            raise PrivacyPolicyError("Offline privacy policy blocks external providers")
        if (
            self._context.privacy_policy is not PrivacyPolicy.STRICT
            or not self._capability.external
        ):
            return list(texts)
        return [
            self._redactor.redact(text, redact_email=True, redact_phone=True)[0] for text in texts
        ]

    def _start_call(
        self,
        *,
        request_hash: str,
        workflow_run_id: int | None,
        attempt: int,
        pricing_snapshot: dict[str, object],
    ) -> int:
        idempotency_key = hashlib.sha256(f"{request_hash}:{uuid4()}".encode()).hexdigest()
        with self._session_factory.begin() as session:
            row = ProviderCallRepository(session).add(
                ProviderCall(
                    project_id=self._context.project_id,
                    workflow_run_id=workflow_run_id,
                    chapter_id=self._context.chapter_id,
                    chapter_version_id=self._context.chapter_version_id,
                    task_type=self._task_type,
                    provider=self._capability.provider,
                    model=self._capability.model,
                    profile=self._context.profile,
                    privacy_policy=self._context.privacy_policy,
                    prompt_name=f"embedding.{self._task_type.value}",
                    prompt_version="v1",
                    request_hash=request_hash,
                    idempotency_key=idempotency_key,
                    status=ProviderCallStatus.RUNNING,
                    attempt=attempt,
                    fallback_index=0,
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
        workflow_run_id: int | None,
        error_code: str | None = None,
    ) -> None:
        with self._session_factory.begin() as session:
            row = ProviderCallRepository(session).get(call_id)
            if row is None:
                raise RuntimeError("Provider call audit row disappeared")
            changes: dict[str, object] = {
                "status": status,
                "latency_ms": latency_ms,
                "error_code": error_code,
                "completed_at": utc_now(),
            }
            if usage is not None:
                changes.update(
                    {
                        "input_tokens": usage.input_tokens,
                        "output_tokens": 0,
                        "total_tokens": usage.total_tokens,
                        "usage_source": usage.source,
                        "estimated_cost": estimated_cost,
                    }
                )
            ProviderCallRepository(session).update(row, changes)
            if workflow_run_id is not None:
                workflow = session.get(WorkflowRun, workflow_run_id)
                if workflow is not None:
                    workflow.provider_call_count += 1
                    workflow.provider_input_tokens += usage.input_tokens if usage else 0
                    workflow.provider_estimated_cost += estimated_cost or Decimal("0")

    def _effective_workflow_run_id(self) -> int | None:
        if self._context.workflow_run_id is not None:
            return self._context.workflow_run_id
        if self._context.project_id is None:
            return None
        with self._session_factory() as session:
            return session.scalar(
                select(WorkflowRun.id)
                .where(
                    WorkflowRun.project_id == self._context.project_id,
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
    def _hash(texts: Sequence[str]) -> str:
        return hashlib.sha256(
            json.dumps(list(texts), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _retryable(error: Exception) -> bool:
        return isinstance(
            error, (EmbeddingTimeoutError, EmbeddingProviderError)
        ) and not isinstance(error, (EmbeddingInvalidResponseError, EmbeddingDimensionError))

    @staticmethod
    def _status_for_error(error: Exception) -> ProviderCallStatus:
        if isinstance(error, BudgetBlockedError):
            return ProviderCallStatus.BUDGET_BLOCKED
        if isinstance(error, EmbeddingTimeoutError):
            return ProviderCallStatus.TIMED_OUT
        if isinstance(error, ProviderRateLimitError):
            return ProviderCallStatus.RATE_LIMITED
        if isinstance(error, CircuitOpenError):
            return ProviderCallStatus.CIRCUIT_OPEN
        return ProviderCallStatus.FAILED
