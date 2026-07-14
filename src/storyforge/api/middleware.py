"""Request correlation, size limits, and metadata-only access logging."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from storyforge.schemas.api import ErrorResponse
from storyforge.settings import Settings

logger = logging.getLogger(__name__)


def install_http_middleware(app: FastAPI, settings: Settings) -> None:
    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied = request.headers.get("X-Request-ID", "").strip()
        request_id = supplied[:128] if supplied else str(uuid4())
        request.state.request_id = request_id
        content_length = request.headers.get("content-length")
        if content_length is not None and _exceeds_limit(
            content_length, settings.max_request_body_bytes
        ):
            body = ErrorResponse(
                error="request_too_large",
                message="Request body exceeds the configured size limit",
                request_id=request_id,
            )
            early_response = JSONResponse(status_code=413, content=body.model_dump(mode="json"))
            early_response.headers["X-Request-ID"] = request_id
            return early_response
        started = perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        if settings.enable_http_logging and request.url.path != "/health":
            duration_ms = max(0, round((perf_counter() - started) * 1000))
            logger.info(
                "http_request method=%s path=%s status=%s duration_ms=%s request_id=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                request_id,
            )
        return response


def _exceeds_limit(raw: str, maximum: int) -> bool:
    try:
        return int(raw) > maximum
    except ValueError:
        return False
