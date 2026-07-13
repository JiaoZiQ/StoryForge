"""Minimal FastAPI application for the repository bootstrap milestone."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from storyforge import __version__


class HealthResponse(BaseModel):
    """Public response returned by the health endpoint."""

    status: Literal["ok"]
    service: str
    version: str


def create_app() -> FastAPI:
    """Create the StoryForge ASGI application."""
    application = FastAPI(
        title="StoryForge",
        description="Multi-agent long-form fiction generation system.",
        version=__version__,
    )

    @application.get(
        "/health",
        response_model=HealthResponse,
        tags=["system"],
        summary="Check service health",
    )
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="storyforge", version=__version__)

    return application


app = create_app()
