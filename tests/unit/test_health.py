"""Tests for the bootstrap health endpoint."""

from fastapi.testclient import TestClient

from storyforge import __version__
from storyforge.api.app import app


def test_health_endpoint_returns_typed_service_metadata() -> None:
    """The service should expose a stable, documented health response."""
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "storyforge",
        "version": __version__,
    }

    health_schema = app.openapi()["paths"]["/health"]["get"]["responses"]["200"]
    assert health_schema["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HealthResponse"
    }
