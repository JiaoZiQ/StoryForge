"""Milestone 12 full-book settings validation."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from storyforge.exceptions import ConfigurationError
from storyforge.settings import Settings


def test_book_settings_load_from_namespaced_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "STORYFORGE_BOOK_DEFAULT_MODE": "dependency_aware",
        "STORYFORGE_BOOK_MAX_ACTIVE_RUNS_PER_PROJECT": "1",
        "STORYFORGE_BOOK_CHAPTER_CONCURRENCY": "3",
        "STORYFORGE_BOOK_GLOBAL_CHECK_INTERVAL": "4",
        "STORYFORGE_BOOK_MAX_CHAPTER_RETRIES": "3",
        "STORYFORGE_BOOK_MAX_GLOBAL_REVISION_ROUNDS": "2",
        "STORYFORGE_BOOK_MAX_REVISION_CHAPTERS_PER_ROUND": "4",
        "STORYFORGE_BOOK_MIN_PASS_SCORE": "7.5",
        "STORYFORGE_BOOK_MIN_FORESHADOWING_PAYOFF_RATE": "0.75",
        "STORYFORGE_BOOK_MAX_COST": "9.50",
        "STORYFORGE_BOOK_MAX_TOKENS": "900000",
        "STORYFORGE_BOOK_MAX_PROVIDER_CALLS": "120",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    settings = Settings.from_env()

    assert settings.book_default_mode == "dependency_aware"
    assert settings.book_chapter_concurrency == 3
    assert settings.book_global_check_interval == 4
    assert settings.book_max_chapter_retries == 3
    assert settings.book_max_global_revision_rounds == 2
    assert settings.book_max_revision_chapters_per_round == 4
    assert settings.book_min_pass_score == 7.5
    assert settings.book_min_foreshadowing_payoff_rate == 0.75
    assert settings.book_max_cost == Decimal("9.50")
    assert settings.book_max_tokens == 900000
    assert settings.book_max_provider_calls == 120


def test_sequential_mode_disallows_parallel_chapter_acceptance() -> None:
    with pytest.raises(ConfigurationError, match="Sequential book mode requires"):
        Settings(book_default_mode="sequential", book_chapter_concurrency=2)


def test_book_concurrency_has_a_hard_upper_bound() -> None:
    with pytest.raises(ValidationError):
        Settings(book_default_mode="dependency_aware", book_chapter_concurrency=5)
