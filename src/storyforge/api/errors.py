"""Stable exception-to-HTTP mapping without infrastructure detail leakage."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from storyforge.exceptions import (
    AgentExecutionError,
    AlreadyExistsError,
    BudgetBlockedError,
    ChapterGenerationError,
    CircuitOpenError,
    ConfigurationError,
    ContextBuildError,
    DatabaseConflictError,
    DatabaseNotReadyError,
    DomainValidationError,
    EntityNotFoundError,
    EvaluationError,
    IdempotencyConflictError,
    InvalidStateError,
    PlanningValidationError,
    PrivacyPolicyError,
    ProviderRateLimitError,
    QueueBackpressureError,
    QueueUnavailableError,
    StoryForgeError,
    WorkflowAlreadyRunningError,
    WorkflowCancelledError,
    WorkflowExecutionError,
    WorkflowNotResumableError,
)
from storyforge.llm.exceptions import (
    LLMConfigurationError,
    LLMProviderError,
    LLMServiceError,
    LLMTimeoutError,
)
from storyforge.schemas.api import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return str(value) if value is not None else None


def _response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[ErrorDetail] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=code,
        message=message,
        details=details or [],
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def _mapping(exc: Exception) -> tuple[int, str, str]:
    if isinstance(exc, DatabaseNotReadyError):
        return 503, "database_not_ready", "The database migrations are incomplete"
    if isinstance(exc, EntityNotFoundError):
        return 404, "resource_not_found", str(exc)
    if isinstance(exc, WorkflowAlreadyRunningError):
        return 409, "workflow_already_running", str(exc)
    if isinstance(exc, WorkflowNotResumableError):
        return 409, "workflow_not_resumable", str(exc)
    if isinstance(exc, WorkflowCancelledError):
        return 409, "workflow_cancelled", str(exc)
    if isinstance(exc, AlreadyExistsError):
        return 409, "already_exists", str(exc)
    if isinstance(exc, DatabaseConflictError | IntegrityError):
        return 409, "database_conflict", "The requested write conflicts with existing data"
    if isinstance(exc, BudgetBlockedError):
        return 409, "budget_blocked", str(exc)
    if isinstance(exc, PrivacyPolicyError):
        return 409, "privacy_policy_blocked", str(exc)
    if isinstance(exc, IdempotencyConflictError):
        return 409, "provider_call_conflict", str(exc)
    if isinstance(exc, ProviderRateLimitError):
        return 503, "provider_rate_limited", "Local provider capacity is exhausted"
    if isinstance(exc, QueueBackpressureError):
        return 429, "queue_backpressure", str(exc)
    if isinstance(exc, QueueUnavailableError):
        return 503, "queue_unavailable", "The asynchronous queue is unavailable"
    if isinstance(exc, CircuitOpenError):
        return 503, "provider_circuit_open", "The configured provider circuit is open"
    if isinstance(exc, InvalidStateError):
        return 409, "state_conflict", str(exc)
    if isinstance(exc, DomainValidationError | PlanningValidationError | ContextBuildError):
        return 422, "domain_validation", str(exc)
    if isinstance(exc, LLMTimeoutError):
        return 504, "provider_timeout", "The configured model provider timed out"
    if isinstance(exc, LLMConfigurationError | ConfigurationError):
        return 503, "provider_configuration", "The application provider is not configured"
    if isinstance(exc, LLMServiceError | LLMProviderError):
        return 503, "provider_unavailable", "The configured model provider is unavailable"
    if isinstance(
        exc,
        AgentExecutionError | ChapterGenerationError | EvaluationError | WorkflowExecutionError,
    ):
        return 503, "operation_unavailable", "The requested operation could not be completed"
    return 500, "internal_error", "An unexpected internal error occurred"


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details: list[ErrorDetail] = []
        for item in exc.errors():
            location = item.get("loc", ())
            field = ".".join(
                str(part) for part in location if part not in {"body", "query", "path"}
            )
            details.append(
                ErrorDetail(
                    code=str(item.get("type", "validation_error")),
                    message=str(item.get("msg", "Invalid input")),
                    field=field or None,
                )
            )
        return _response(
            request,
            status_code=422,
            code="validation_error",
            message="Request validation failed",
            details=details,
        )

    @app.exception_handler(StoryForgeError)
    @app.exception_handler(LLMProviderError)
    @app.exception_handler(LLMConfigurationError)
    async def known_error(request: Request, exc: Exception) -> JSONResponse:
        status_code, code, message = _mapping(exc)
        response = _response(request, status_code=status_code, code=code, message=message)
        if isinstance(exc, QueueBackpressureError):
            response.headers["Retry-After"] = str(exc.retry_after)
        return response

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning(
            "database_conflict request_id=%s exception_type=%s",
            _request_id(request),
            type(exc).__name__,
        )
        status_code, code, message = _mapping(exc)
        return _response(request, status_code=status_code, code=code, message=message)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error(
            "database_error request_id=%s exception_type=%s",
            _request_id(request),
            type(exc).__name__,
        )
        return _response(
            request,
            status_code=503,
            code="database_unavailable",
            message="The database is unavailable",
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unexpected_error request_id=%s exception_type=%s",
            _request_id(request),
            type(exc).__name__,
        )
        return _response(
            request,
            status_code=500,
            code="internal_error",
            message="An unexpected internal error occurred",
        )


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Resource not found"},
    409: {"model": ErrorResponse, "description": "State or write conflict"},
    429: {"model": ErrorResponse, "description": "Queue backpressure"},
    422: {"model": ErrorResponse, "description": "Validation failed"},
    503: {"model": ErrorResponse, "description": "Dependency unavailable"},
    504: {"model": ErrorResponse, "description": "Provider timeout"},
}
