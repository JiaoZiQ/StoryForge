"""Pydantic v2 validation tests for domain boundaries."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session
from tests._factories import make_project

from storyforge.schemas import (
    ChapterCreate,
    CharacterCreate,
    EvaluationCreate,
    FactCreate,
    FactUpdate,
    ForeshadowingCreate,
    LocationCreate,
    ProjectCreate,
    ProjectRead,
    RevisionCreate,
    RevisionUpdate,
    StoryRuleCreate,
    WorkflowRunCreate,
)


def test_all_entity_create_schemas_accept_valid_payloads() -> None:
    """Every persistence entity should have a concrete validated request model."""
    project = ProjectCreate(
        title="Story",
        genre="Fantasy",
        premise="A city wakes beneath the sea.",
        target_chapters=8,
        target_words_per_chapter=2000,
    )
    payloads = [
        project,
        CharacterCreate(
            project_id=1,
            name="Mara",
            role="lead",
            description="A diver.",
            goals=["Find the city"],
            personality="Patient.",
            speech_style="Direct.",
            current_state="At sea.",
            secrets=[],
        ),
        LocationCreate(
            project_id=1,
            name="Sunken City",
            description="A city below the waves.",
            rules=["Bells keep the water out"],
        ),
        StoryRuleCreate(
            project_id=1,
            category="world",
            statement="The bells must ring hourly.",
            source="premise",
        ),
        ChapterCreate(
            project_id=1,
            chapter_number=1,
            title="The First Bell",
            outline="Mara hears the bell.",
        ),
        FactCreate(
            project_id=1,
            chapter_id=1,
            subject="bell",
            predicate="rings_at",
            object="noon",
            valid_from_chapter=1,
            confidence=0.9,
            source_quote="The bell rang at noon.",
        ),
        ForeshadowingCreate(
            project_id=1,
            setup_chapter=1,
            expected_payoff_chapter=4,
            description="A cracked bell is hidden.",
        ),
        EvaluationCreate(
            project_id=1,
            chapter_id=1,
            evaluator="critic",
            overall_score=80,
            consistency_score=90,
            prose_score=75,
            character_score=78,
            plot_score=77,
        ),
        RevisionCreate(
            chapter_id=1,
            previous_version=1,
            new_version=2,
            reason="Improve pacing.",
            score_before=75,
            score_after=80,
        ),
        WorkflowRunCreate(
            project_id=1,
            chapter_id=1,
            current_node="draft_chapter",
        ),
    ]
    assert len(payloads) == 10
    assert project.title == "Story"


def test_response_schema_reads_sqlalchemy_attributes(session: Session) -> None:
    """Responses should validate ORM entities without leaking ORM internals."""
    project = make_project(title="  Trimmed Story  ")
    session.add(project)
    session.flush()

    response = ProjectRead.model_validate(project)

    assert response.id == project.id
    assert response.title == "Trimmed Story"


def test_fact_schema_rejects_reversed_chapter_range() -> None:
    """Fact validity cannot end before it starts."""
    with pytest.raises(ValidationError, match="valid_to_chapter"):
        FactCreate(
            project_id=1,
            chapter_id=1,
            subject="Mara",
            predicate="location",
            object="Harbor",
            valid_from_chapter=4,
            valid_to_chapter=3,
            confidence=1,
            source_quote="Mara stood in the harbor.",
        )


def test_update_schemas_enforce_cross_field_invariants() -> None:
    """Partial updates should validate complete fact and revision relations."""
    with pytest.raises(ValidationError, match="valid_to_chapter"):
        FactUpdate(valid_from_chapter=4, valid_to_chapter=3)
    assert FactUpdate(subject="Mara").subject == "Mara"

    with pytest.raises(ValidationError, match="new_version"):
        RevisionUpdate(previous_version=2, new_version=2)
    assert RevisionUpdate(reason="Improve pacing.").reason == "Improve pacing."


@pytest.mark.parametrize(
    ("expected_payoff_chapter", "payoff_chapter", "error_field"),
    [(2, None, "expected_payoff_chapter"), (4, 2, "payoff_chapter")],
)
def test_foreshadowing_schema_rejects_payoff_before_setup(
    expected_payoff_chapter: int,
    payoff_chapter: int | None,
    error_field: str,
) -> None:
    """Expected and actual payoff chapters cannot precede their setup."""
    with pytest.raises(ValidationError, match=error_field):
        ForeshadowingCreate(
            project_id=1,
            setup_chapter=3,
            expected_payoff_chapter=expected_payoff_chapter,
            description="A bell is hidden.",
            payoff_chapter=payoff_chapter,
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("overall_score", 101), ("prose_score", -1)],
)
def test_evaluation_schema_rejects_out_of_range_scores(
    field_name: str,
    value: float,
) -> None:
    """All evaluation dimensions must stay within 0..100."""
    values: dict[str, object] = {
        "project_id": 1,
        "chapter_id": 1,
        "evaluator": "critic",
        "overall_score": 80,
        "consistency_score": 80,
        "prose_score": 80,
        "character_score": 80,
        "plot_score": 80,
    }
    values[field_name] = value
    with pytest.raises(ValidationError):
        EvaluationCreate.model_validate(values)


def test_revision_schema_requires_forward_version_progression() -> None:
    """A revision cannot keep or lower the chapter version."""
    with pytest.raises(ValidationError, match="new_version"):
        RevisionCreate(
            chapter_id=1,
            previous_version=2,
            new_version=2,
            reason="No progression.",
            score_before=80,
            score_after=80,
        )


def test_workflow_schema_rejects_finish_before_start() -> None:
    """Workflow timestamps should be chronologically ordered."""
    started_at = datetime.now(UTC)
    with pytest.raises(ValidationError, match="finished_at"):
        WorkflowRunCreate(
            project_id=1,
            chapter_id=1,
            current_node="load_context",
            started_at=started_at,
            finished_at=started_at - timedelta(seconds=1),
        )
