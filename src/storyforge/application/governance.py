"""Provider registry, usage, budget, and project policy application service."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from storyforge.database import SessionFactory
from storyforge.enums import (
    ModelProfile,
    PrivacyPolicy,
    ProviderCallStatus,
    TaskType,
    WorkflowRunStatus,
)
from storyforge.exceptions import EntityNotFoundError, InvalidStateError
from storyforge.models import Project, ProjectBudget, WorkflowRun
from storyforge.repositories import ProjectRepository, WorkflowRunRepository
from storyforge.schemas.api import (
    ModelProfileOption,
    PageResponse,
    ProjectBudgetResponse,
    ProjectBudgetUpdateRequest,
    ProjectModelSettingsResponse,
    ProviderCallResponse,
    ProviderCapabilityResponse,
    ProviderHealthResponse,
    UsageSummaryResponse,
)
from storyforge.usage import BudgetService, UsageService
from storyforge.usage.repositories import ProviderCallRepository

from .common import page_response
from .factory import DomainServiceFactory


class GovernanceApplicationService:
    """Expose content-free control-plane projections to HTTP and CLI adapters."""

    def __init__(
        self,
        session_factory: SessionFactory,
        factory: DomainServiceFactory,
    ) -> None:
        self._session_factory = session_factory
        self._factory = factory
        self._budget = BudgetService(session_factory, factory.settings)
        self._usage = UsageService(session_factory, factory.settings.default_currency)

    def providers(self) -> list[ProviderCapabilityResponse]:
        return [
            ProviderCapabilityResponse(
                provider=item.provider,
                model=item.model,
                model_type=item.model_type,
                context_window=item.context_window,
                max_output_tokens=item.max_output_tokens,
                supports_structured_output=item.supports_structured_output,
                supports_json_schema=item.supports_json_schema,
                supports_embeddings=item.supports_embeddings,
                embedding_dimensions=item.embedding_dimensions,
                enabled=item.enabled,
                pricing_available=item.pricing_known,
            )
            for item in self._factory.provider_registry.list()
        ]

    def health(self) -> list[ProviderHealthResponse]:
        results: list[ProviderHealthResponse] = []
        for item in self._factory.provider_registry.list():
            snapshot = self._factory.circuit_breaker.snapshot(f"{item.provider}/{item.model}")
            capabilities: list[str] = [item.model_type]
            if item.supports_structured_output:
                capabilities.append("structured_output")
            if item.supports_json_schema:
                capabilities.append("json_schema")
            if item.supports_embeddings:
                capabilities.append("embeddings")
            results.append(
                ProviderHealthResponse(
                    provider=item.provider,
                    model=item.model,
                    enabled=item.enabled,
                    health_status=("configured" if item.enabled else "disabled"),
                    circuit_status=snapshot.state.value,
                    pricing_available=item.pricing_known,
                    capabilities=capabilities,
                )
            )
        return results

    def usage_summary(
        self,
        *,
        project_id: int | None = None,
        workflow_run_id: int | None = None,
        task_type: TaskType | None = None,
        provider: str | None = None,
        model: str | None = None,
        status: ProviderCallStatus | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> UsageSummaryResponse:
        if workflow_run_id is not None:
            self._require_workflow(workflow_run_id)
        summary = self._usage.summary(
            project_id,
            workflow_run_id=workflow_run_id,
            task_type=task_type,
            provider=provider,
            model=model,
            status=status,
            created_from=created_from,
            created_to=created_to,
        )
        return UsageSummaryResponse(**summary.model_dump())

    def usage_calls(
        self,
        *,
        page: int,
        page_size: int,
        project_id: int | None = None,
        workflow_run_id: int | None = None,
        task_type: TaskType | None = None,
        provider: str | None = None,
        model: str | None = None,
        status: ProviderCallStatus | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> PageResponse[ProviderCallResponse]:
        with self._session_factory() as session:
            if project_id is not None and ProjectRepository(session).get(project_id) is None:
                raise EntityNotFoundError(f"Project {project_id} was not found")
            result = ProviderCallRepository(session).page_filtered(
                page=page,
                page_size=page_size,
                project_id=project_id,
                workflow_run_id=workflow_run_id,
                task_type=task_type,
                provider=provider,
                model=model,
                status=status,
                created_from=created_from,
                created_to=created_to,
            )
            items = [
                ProviderCallResponse.model_validate(item, from_attributes=True)
                for item in result.items
            ]
        return page_response(result, page=page, page_size=page_size, items=items)

    def budget(self, project_id: int) -> ProjectBudgetResponse:
        return _budget_response(self._budget.get_or_create(project_id))

    def set_budget(
        self, project_id: int, request: ProjectBudgetUpdateRequest
    ) -> ProjectBudgetResponse:
        return _budget_response(self._budget.set(project_id, **request.model_dump()))

    def model_settings(self, project_id: int) -> ProjectModelSettingsResponse:
        with self._session_factory() as session:
            project = ProjectRepository(session).get(project_id)
            if project is None:
                raise EntityNotFoundError(f"Project {project_id} was not found")
            return _model_settings_response(project)

    def set_model_profile(
        self, project_id: int, profile: ModelProfile
    ) -> ProjectModelSettingsResponse:
        with self._session_factory.begin() as session:
            project = self._mutable_project(session, project_id)
            if (
                profile is ModelProfile.OFFLINE
                and project.privacy_policy is not PrivacyPolicy.OFFLINE
            ):
                raise InvalidStateError("Offline profile requires offline privacy policy")
            project.model_profile = profile
        return self.model_settings(project_id)

    def set_privacy_policy(
        self, project_id: int, policy: PrivacyPolicy
    ) -> ProjectModelSettingsResponse:
        with self._session_factory.begin() as session:
            project = self._mutable_project(session, project_id)
            if (
                policy is not PrivacyPolicy.OFFLINE
                and project.model_profile is ModelProfile.OFFLINE
            ):
                raise InvalidStateError("Select a non-offline model profile first")
            project.privacy_policy = policy
        return self.model_settings(project_id)

    @staticmethod
    def model_profiles() -> list[ModelProfileOption]:
        descriptions = {
            ModelProfile.OFFLINE: "Mock or local models only; no external data transfer.",
            ModelProfile.ECONOMY: "Registered cost-focused routes with bounded fallbacks.",
            ModelProfile.BALANCED: "Registered balanced quality and cost routes.",
            ModelProfile.QUALITY: "Registered quality-focused routes within budget.",
        }
        return [
            ModelProfileOption(
                name=profile,
                description=descriptions[profile],
                external_allowed=profile is not ModelProfile.OFFLINE,
            )
            for profile in ModelProfile
        ]

    def _mutable_project(self, session: Session, project_id: int) -> Project:
        project = ProjectRepository(session).get(project_id)
        if project is None:
            raise EntityNotFoundError(f"Project {project_id} was not found")
        running = session.scalar(
            select(WorkflowRun.id).where(
                WorkflowRun.project_id == project_id,
                WorkflowRun.status.in_(
                    (
                        WorkflowRunStatus.PENDING,
                        WorkflowRunStatus.RUNNING,
                        WorkflowRunStatus.PAUSED,
                    )
                ),
            )
        )
        if running is not None:
            raise InvalidStateError("Model settings cannot change during an active workflow")
        return project

    def _require_workflow(self, workflow_run_id: int) -> None:
        with self._session_factory() as session:
            if WorkflowRunRepository(session).get(workflow_run_id) is None:
                raise EntityNotFoundError(f"Workflow run {workflow_run_id} was not found")


def _budget_response(budget: ProjectBudget) -> ProjectBudgetResponse:
    remaining = budget.hard_limit - budget.spent_estimated - budget.reserved_estimated
    return ProjectBudgetResponse(
        project_id=budget.project_id,
        currency=budget.currency,
        soft_limit=budget.soft_limit,
        hard_limit=budget.hard_limit,
        period=budget.period,
        spent_estimated=budget.spent_estimated,
        spent_billed=budget.spent_billed,
        reserved_estimated=budget.reserved_estimated,
        alert_thresholds=list(budget.alert_thresholds),
        enabled=budget.enabled,
        remaining_estimated=remaining if remaining > Decimal("0") else Decimal("0"),
    )


def _model_settings_response(project: Project) -> ProjectModelSettingsResponse:
    return ProjectModelSettingsResponse(
        project_id=project.id,
        model_profile=project.model_profile,
        privacy_policy=project.privacy_policy,
    )
