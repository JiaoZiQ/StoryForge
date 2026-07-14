"""FastAPI application factory with lifespan-owned infrastructure."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from storyforge import __version__
from storyforge.database import create_database_engine, create_session_factory
from storyforge.settings import Settings

from .errors import install_exception_handlers
from .middleware import install_http_middleware
from .routes import api_router, root_router


class StoryForgeAPI(FastAPI):
    """FastAPI application with complete operation descriptions in OpenAPI."""

    def openapi(self) -> dict[str, Any]:
        if self.openapi_schema is None:
            schema = get_openapi(
                title=self.title,
                version=self.version,
                openapi_version=self.openapi_version,
                summary=self.summary,
                description=self.description,
                routes=self.routes,
                tags=self.openapi_tags,
                servers=self.servers,
            )
            for path_item in schema.get("paths", {}).values():
                for operation in path_item.values():
                    operation.setdefault("description", operation.get("summary", "Operation"))
            self.openapi_schema = schema
        return self.openapi_schema


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an isolated application without import-time database connections."""
    configured = settings or Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, configured.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(configured.database_url)
        application.state.settings = configured
        application.state.engine = engine
        application.state.session_factory = create_session_factory(engine)
        try:
            yield
        finally:
            engine.dispose()

    application = StoryForgeAPI(
        title="StoryForge API",
        summary="Generate, evaluate, revise, and audit long-form story chapters.",
        description=(
            "Milestone 6 exposes synchronous application services over a versioned REST API. "
            "Chapter workflows complete before their 201 response; no background worker is implied."
        ),
        version=__version__,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "system", "description": "Liveness and readiness."},
            {"name": "projects", "description": "Project lifecycle."},
            {"name": "planning", "description": "Structured story planning."},
            {"name": "chapters", "description": "Logical chapter operations."},
            {"name": "versions", "description": "Immutable chapter versions."},
            {"name": "evaluations", "description": "Evaluation history and detail."},
            {"name": "conflicts", "description": "Consistency conflict review."},
            {"name": "facts", "description": "Accepted canonical facts only."},
            {"name": "workflows", "description": "Durable synchronous workflows."},
        ],
    )
    install_http_middleware(application, configured)
    install_exception_handlers(application)
    application.include_router(root_router)
    application.include_router(api_router, prefix=configured.api_prefix)
    return application


# Compatibility object for tests and simple local imports. Production/development
# configuration uses the documented Uvicorn ``--factory`` entry so importing this
# module never reads a real credential from process environment.
app = create_app(Settings())
