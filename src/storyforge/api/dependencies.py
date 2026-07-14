"""FastAPI dependency providers backed by application lifespan state."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from storyforge.application import (
    ChapterApplicationService,
    DomainServiceFactory,
    EvaluationApplicationService,
    PlanningApplicationService,
    ProjectApplicationService,
    SystemApplicationService,
    WorkflowApplicationService,
)
from storyforge.database import SessionFactory
from storyforge.llm import LLMProvider
from storyforge.settings import Settings


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_session_factory(request: Request) -> SessionFactory:
    return cast(SessionFactory, request.app.state.session_factory)


def get_db_session(
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
) -> Iterator[Session]:
    """Yield a request-scoped diagnostic session with safe rollback semantics."""
    session = session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_domain_factory(
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DomainServiceFactory:
    return DomainServiceFactory(session_factory, settings)


def get_llm_provider(
    factory: Annotated[DomainServiceFactory, Depends(get_domain_factory)],
) -> Iterator[LLMProvider]:
    """Yield a test-overridable provider dependency without caching credentials."""
    with factory.provider("evaluation") as provider:
        yield provider


def get_project_service(
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
) -> ProjectApplicationService:
    return ProjectApplicationService(session_factory)


def get_planning_service(
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
    factory: Annotated[DomainServiceFactory, Depends(get_domain_factory)],
) -> PlanningApplicationService:
    return PlanningApplicationService(session_factory, factory)


def get_chapter_service(
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
    factory: Annotated[DomainServiceFactory, Depends(get_domain_factory)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChapterApplicationService:
    return ChapterApplicationService(session_factory, factory, settings)


def get_evaluation_service(
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
    factory: Annotated[DomainServiceFactory, Depends(get_domain_factory)],
) -> EvaluationApplicationService:
    return EvaluationApplicationService(session_factory, factory)


def get_workflow_service(
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
    factory: Annotated[DomainServiceFactory, Depends(get_domain_factory)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WorkflowApplicationService:
    return WorkflowApplicationService(session_factory, factory, settings)


def get_system_service(
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SystemApplicationService:
    return SystemApplicationService(session_factory, settings)


ProjectServiceDep = Annotated[ProjectApplicationService, Depends(get_project_service)]
PlanningServiceDep = Annotated[PlanningApplicationService, Depends(get_planning_service)]
ChapterServiceDep = Annotated[ChapterApplicationService, Depends(get_chapter_service)]
EvaluationServiceDep = Annotated[EvaluationApplicationService, Depends(get_evaluation_service)]
WorkflowServiceDep = Annotated[WorkflowApplicationService, Depends(get_workflow_service)]
SystemServiceDep = Annotated[SystemApplicationService, Depends(get_system_service)]
