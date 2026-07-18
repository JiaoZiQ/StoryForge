"""Transactional budgets and aggregate provider usage."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from storyforge.database import SessionFactory
from storyforge.enums import BudgetPeriod, ProviderCallStatus, TaskType
from storyforge.exceptions import BudgetBlockedError, EntityNotFoundError
from storyforge.models import ProjectBudget, WorkflowRun
from storyforge.repositories import ProjectRepository
from storyforge.settings import Settings
from storyforge.usage.models import BudgetDecision, UsageSummary
from storyforge.usage.repositories import ProjectBudgetRepository, ProviderCallRepository


class BudgetService:
    """Reserve estimated money before provider calls and settle it atomically afterward."""

    def __init__(self, session_factory: SessionFactory, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings

    def get_or_create(self, project_id: int) -> ProjectBudget:
        with self._session_factory.begin() as session:
            if ProjectRepository(session).get(project_id) is None:
                raise EntityNotFoundError(f"Project {project_id} was not found")
            repository = ProjectBudgetRepository(session)
            budget = repository.for_project(project_id, lock=True)
            if budget is None:
                budget = repository.add(
                    ProjectBudget(
                        project_id=project_id,
                        currency=self._settings.default_currency,
                        soft_limit=self._settings.project_soft_budget,
                        hard_limit=self._settings.project_hard_budget,
                        period=BudgetPeriod.LIFETIME,
                        spent_estimated=Decimal("0"),
                        spent_billed=Decimal("0"),
                        reserved_estimated=Decimal("0"),
                        alert_thresholds=["0.5", "0.8", "1.0"],
                        enabled=True,
                    )
                )
            session.expunge(budget)
            return budget

    def set(
        self,
        project_id: int,
        *,
        soft_limit: Decimal,
        hard_limit: Decimal,
        currency: str,
        period: BudgetPeriod,
        enabled: bool,
    ) -> ProjectBudget:
        if soft_limit < 0 or hard_limit <= 0 or soft_limit > hard_limit:
            raise ValueError("Budget limits are invalid")
        with self._session_factory.begin() as session:
            repository = ProjectBudgetRepository(session)
            budget = repository.for_project(project_id, lock=True)
            if budget is None:
                if ProjectRepository(session).get(project_id) is None:
                    raise EntityNotFoundError(f"Project {project_id} was not found")
                budget = repository.add(
                    ProjectBudget(
                        project_id=project_id,
                        currency=currency,
                        soft_limit=soft_limit,
                        hard_limit=hard_limit,
                        period=period,
                        spent_estimated=Decimal("0"),
                        spent_billed=Decimal("0"),
                        reserved_estimated=Decimal("0"),
                        alert_thresholds=["0.5", "0.8", "1.0"],
                        enabled=enabled,
                    )
                )
            else:
                if hard_limit < budget.spent_estimated + budget.reserved_estimated:
                    raise BudgetBlockedError("Hard budget cannot be lower than current usage")
                repository.update(
                    budget,
                    {
                        "soft_limit": soft_limit,
                        "hard_limit": hard_limit,
                        "currency": currency,
                        "period": period,
                        "enabled": enabled,
                    },
                )
            session.expunge(budget)
            return budget

    def reserve(self, project_id: int, estimated_cost: Decimal | None) -> BudgetDecision:
        if estimated_cost is None:
            if not self._settings.allow_unknown_pricing:
                raise BudgetBlockedError("Unknown model pricing is blocked by policy")
            estimated_cost = Decimal("0")
        self.get_or_create(project_id)
        with self._session_factory.begin() as session:
            budget = ProjectBudgetRepository(session).for_project(project_id, lock=True)
            if budget is None:
                raise RuntimeError("Project budget disappeared during reservation")
            if not budget.enabled:
                return BudgetDecision(allowed=True, warning=False, reason="budget_disabled")
            projected = budget.spent_estimated + budget.reserved_estimated + estimated_cost
            if projected > budget.hard_limit:
                raise BudgetBlockedError("Project hard budget would be exceeded")
            budget.reserved_estimated += estimated_cost
            warning = projected >= budget.soft_limit
            return BudgetDecision(
                allowed=True,
                warning=warning,
                reason="soft_limit_warning" if warning else "within_budget",
                reserved_amount=estimated_cost,
            )

    def check_workflow(
        self,
        workflow_run_id: int | None,
        *,
        estimated_cost: Decimal | None,
        estimated_tokens: int,
    ) -> None:
        """Enforce persisted workflow call, token, and cost ceilings before a call."""
        if workflow_run_id is None:
            return
        with self._session_factory.begin() as session:
            workflow = session.get(WorkflowRun, workflow_run_id, with_for_update=True)
            if workflow is None:
                raise EntityNotFoundError(f"Workflow run {workflow_run_id} was not found")
            if workflow.provider_call_count + 1 > self._settings.workflow_max_provider_calls:
                raise BudgetBlockedError("Workflow provider call limit would be exceeded")
            used_tokens = workflow.provider_input_tokens + workflow.provider_output_tokens
            if used_tokens + estimated_tokens > self._settings.workflow_max_tokens:
                raise BudgetBlockedError("Workflow token limit would be exceeded")
            if estimated_cost is None and not self._settings.allow_unknown_pricing:
                raise BudgetBlockedError("Unknown workflow pricing is blocked by policy")
            if (
                estimated_cost is not None
                and workflow.provider_estimated_cost + estimated_cost
                > self._settings.workflow_max_cost
            ):
                raise BudgetBlockedError("Workflow estimated cost limit would be exceeded")

    def settle(
        self,
        project_id: int,
        *,
        reserved: Decimal,
        estimated_cost: Decimal | None,
        billed_cost: Decimal | None = None,
    ) -> None:
        with self._session_factory.begin() as session:
            budget = ProjectBudgetRepository(session).for_project(project_id, lock=True)
            if budget is None:
                return
            budget.reserved_estimated = max(Decimal("0"), budget.reserved_estimated - reserved)
            if estimated_cost is not None:
                budget.spent_estimated += estimated_cost
            if billed_cost is not None:
                budget.spent_billed += billed_cost

    def release(self, project_id: int, reserved: Decimal) -> None:
        self.settle(project_id, reserved=reserved, estimated_cost=None)


class UsageService:
    """Read content-free provider usage without exposing prompt or credentials."""

    def __init__(self, session_factory: SessionFactory, currency: str = "USD") -> None:
        self._session_factory = session_factory
        self._currency = currency

    def summary(
        self,
        project_id: int | None = None,
        *,
        workflow_run_id: int | None = None,
        task_type: TaskType | None = None,
        provider: str | None = None,
        model: str | None = None,
        status: ProviderCallStatus | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> UsageSummary:
        with self._session_factory() as session:
            if project_id is not None and ProjectRepository(session).get(project_id) is None:
                raise EntityNotFoundError(f"Project {project_id} was not found")
            calls = ProviderCallRepository(session).filtered(
                project_id=project_id,
                workflow_run_id=workflow_run_id,
                task_type=task_type,
                provider=provider,
                model=model,
                status=status,
                created_from=created_from,
                created_to=created_to,
            )
        succeeded = sum(item.status is ProviderCallStatus.SUCCEEDED for item in calls)
        estimated_cost_unknown = any(
            item.status is ProviderCallStatus.SUCCEEDED and item.estimated_cost is None
            for item in calls
        )
        billed_values = [item.billed_cost for item in calls if item.billed_cost is not None]
        latency_total = sum(item.latency_ms for item in calls)
        return UsageSummary(
            calls=len(calls),
            succeeded=succeeded,
            failures=len(calls) - succeeded,
            input_tokens=sum(item.input_tokens for item in calls),
            output_tokens=sum(item.output_tokens for item in calls),
            cached_input_tokens=sum(item.cached_input_tokens for item in calls),
            total_tokens=sum(item.total_tokens for item in calls),
            estimated_cost=(
                None
                if estimated_cost_unknown
                else sum((item.estimated_cost or Decimal("0") for item in calls), Decimal("0"))
            ),
            billed_cost=(sum(billed_values, Decimal("0")) if billed_values else None),
            fallback_count=sum(item.fallback_index > 0 for item in calls),
            timeout_count=sum(item.status is ProviderCallStatus.TIMED_OUT for item in calls),
            rate_limit_count=sum(item.status is ProviderCallStatus.RATE_LIMITED for item in calls),
            average_latency_ms=(
                Decimal(latency_total) / Decimal(len(calls)) if calls else Decimal("0")
            ),
            currency=self._currency,
        )
