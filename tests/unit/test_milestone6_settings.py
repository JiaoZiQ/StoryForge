"""Configuration safety and API boundary validation."""

import pytest
from pydantic import ValidationError

from storyforge.exceptions import ConfigurationError
from storyforge.schemas.api import ScoreRange
from storyforge.settings import Settings


def test_settings_use_prefixed_environment_and_hide_secrets() -> None:
    settings = Settings.from_env(
        {
            "STORYFORGE_ENVIRONMENT": "test",
            "STORYFORGE_DATABASE_URL": "sqlite:///:memory:",
            "STORYFORGE_LLM_PROVIDER": "openai-compatible",
            "STORYFORGE_LLM_MODEL": "test-model",
            "STORYFORGE_LLM_API_KEY": "sk-test-secret",
        }
    )
    assert settings.llm_api_key is not None
    assert "sk-test-secret" not in repr(settings)
    assert settings.llm_api_key.get_secret_value() == "sk-test-secret"


def test_production_does_not_fall_back_to_mock_or_missing_credentials() -> None:
    with pytest.raises(ConfigurationError, match="Production"):
        Settings(environment="production", llm_provider="mock")
    with pytest.raises(ConfigurationError, match="API key"):
        Settings(llm_provider="openai-compatible", llm_model="real-model")


def test_cross_field_score_range_is_validated() -> None:
    with pytest.raises(ValidationError, match="min_score"):
        ScoreRange(min_score=8, max_score=7)
