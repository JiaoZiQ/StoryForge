"""Database access for provider audit, budgets, and idempotency."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from storyforge.enums import ProviderCallStatus, TaskType
from storyforge.models import (
    ProjectBudget,
    ProviderCall,
    ProviderIdempotencyRecord,
)
from storyforge.repositories.base import PageSlice, Repository


class ProjectBudgetRepository(Repository[ProjectBudget]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ProjectBudget)

    def for_project(self, project_id: int, *, lock: bool = False) -> ProjectBudget | None:
        statement = select(ProjectBudget).where(ProjectBudget.project_id == project_id)
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)


class ProviderCallRepository(Repository[ProviderCall]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ProviderCall)

    def page_filtered(
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
    ) -> PageSlice[ProviderCall]:
        statement = self._filtered_statement(
            project_id=project_id,
            workflow_run_id=workflow_run_id,
            task_type=task_type,
            provider=provider,
            model=model,
            status=status,
            created_from=created_from,
            created_to=created_to,
        )
        return self.paginate(
            statement.order_by(ProviderCall.created_at.desc(), ProviderCall.id.desc()),
            page=page,
            page_size=page_size,
        )

    def filtered(
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
    ) -> list[ProviderCall]:
        statement = self._filtered_statement(
            project_id=project_id,
            workflow_run_id=workflow_run_id,
            task_type=task_type,
            provider=provider,
            model=model,
            status=status,
            created_from=created_from,
            created_to=created_to,
        )
        return list(self.session.scalars(statement.order_by(ProviderCall.id)))

    @staticmethod
    def _filtered_statement(
        *,
        project_id: int | None,
        workflow_run_id: int | None,
        task_type: TaskType | None,
        provider: str | None,
        model: str | None,
        status: ProviderCallStatus | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> Select[tuple[ProviderCall]]:
        statement: Select[tuple[ProviderCall]] = select(ProviderCall)
        filters = (
            (ProviderCall.project_id == project_id) if project_id is not None else None,
            (ProviderCall.workflow_run_id == workflow_run_id)
            if workflow_run_id is not None
            else None,
            (ProviderCall.task_type == task_type) if task_type is not None else None,
            (ProviderCall.provider == provider) if provider is not None else None,
            (ProviderCall.model == model) if model is not None else None,
            (ProviderCall.status == status) if status is not None else None,
            (ProviderCall.created_at >= created_from) if created_from is not None else None,
            (ProviderCall.created_at <= created_to) if created_to is not None else None,
        )
        for condition in filters:
            if condition is not None:
                statement = statement.where(condition)
        return statement

    def for_project(self, project_id: int) -> list[ProviderCall]:
        return list(
            self.session.scalars(
                select(ProviderCall)
                .where(ProviderCall.project_id == project_id)
                .order_by(ProviderCall.id)
            )
        )

    def count_for_workflow(self, workflow_run_id: int) -> int:
        return (
            self.session.scalar(
                select(func.count(ProviderCall.id)).where(
                    ProviderCall.workflow_run_id == workflow_run_id
                )
            )
            or 0
        )


class ProviderIdempotencyRepository(Repository[ProviderIdempotencyRecord]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ProviderIdempotencyRecord)

    def for_key(self, key: str, *, lock: bool = False) -> ProviderIdempotencyRecord | None:
        statement = select(ProviderIdempotencyRecord).where(
            ProviderIdempotencyRecord.idempotency_key == key
        )
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)
