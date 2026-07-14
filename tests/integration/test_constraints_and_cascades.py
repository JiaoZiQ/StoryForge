"""Integration tests for relational constraints and cascade behavior."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests._factories import create_story_graph, make_chapter, make_project

from storyforge.models import (
    Chapter,
    Character,
    EntityBase,
    Evaluation,
    Fact,
    Foreshadowing,
    Location,
    Project,
    Revision,
    StoryRule,
    WorkflowRun,
)
from storyforge.repositories import ChapterRepository, ProjectRepository


def count_rows(session: Session, model_type: type[EntityBase]) -> int:
    """Count persisted rows for one mapped entity."""
    count = session.scalar(select(func.count()).select_from(model_type))
    assert count is not None
    return count


def test_project_delete_cascades_to_all_owned_data(session: Session) -> None:
    """Deleting a project must remove every directly or indirectly owned record."""
    graph = create_story_graph(session)
    project_id = graph.project.id
    session.commit()
    session.expunge_all()

    project = ProjectRepository(session).get(project_id)
    assert project is not None
    ProjectRepository(session).delete(project)
    session.commit()

    for model_type in (
        WorkflowRun,
        Revision,
        Evaluation,
        Fact,
        Foreshadowing,
        Chapter,
        StoryRule,
        Location,
        Character,
        Project,
    ):
        assert count_rows(session, model_type) == 0


def test_chapter_delete_cascades_chapter_scoped_records(session: Session) -> None:
    """Deleting a chapter should retain the project but remove chapter-owned rows."""
    graph = create_story_graph(session)
    chapter_id = graph.chapter.id
    session.commit()
    session.expunge_all()

    chapter = ChapterRepository(session).get(chapter_id)
    assert chapter is not None
    ChapterRepository(session).delete(chapter)
    session.commit()

    assert count_rows(session, Project) == 1
    assert count_rows(session, Character) == 1
    for model_type in (WorkflowRun, Revision, Evaluation, Fact, Chapter):
        assert count_rows(session, model_type) == 0


def test_chapter_number_is_unique_within_project(session: Session) -> None:
    """Projects may both have chapter one, but one project cannot have two of them."""
    first_project = make_project(title="First")
    second_project = make_project(title="Second")
    session.add_all([first_project, second_project])
    session.flush()
    session.add_all([make_chapter(first_project.id), make_chapter(second_project.id)])
    session.commit()

    session.add(make_chapter(first_project.id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    assert count_rows(session, Chapter) == 2


def test_fact_chapter_range_is_enforced_by_database(session: Session) -> None:
    """The database must reject facts whose end chapter precedes their start."""
    graph = create_story_graph(session)
    session.commit()
    invalid_fact = Fact(
        project_id=graph.project.id,
        chapter_id=graph.chapter.id,
        chapter_version_id=graph.chapter_version.id,
        normalized_hash="invalid-range",
        subject="Mara",
        predicate="location",
        object="Harbor",
        valid_from_chapter=3,
        valid_to_chapter=2,
        confidence=1,
        source_quote="Mara entered the harbor.",
    )
    session.add(invalid_fact)

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_evaluation_score_range_is_enforced_by_database(session: Session) -> None:
    """The database must reject any score outside 0..100."""
    graph = create_story_graph(session)
    session.commit()
    invalid_evaluation = Evaluation(
        project_id=graph.project.id,
        chapter_id=graph.chapter.id,
        chapter_version_id=graph.chapter_version.id,
        evaluation_version=2,
        evaluator="invalid-critic",
        overall_score=101,
        consistency_score=80,
        prose_score=80,
        character_score=80,
        plot_score=80,
        issues=[],
        suggestions=[],
    )
    session.add(invalid_evaluation)

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_revision_version_relation_is_enforced_by_database(session: Session) -> None:
    """The database must reject non-advancing revision versions."""
    graph = create_story_graph(session)
    session.commit()
    invalid_revision = Revision(
        chapter_id=graph.chapter.id,
        previous_version=2,
        new_version=2,
        reason="No actual version change.",
        score_before=80,
        score_after=80,
        accepted=False,
    )
    session.add(invalid_revision)

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_revision_new_version_is_unique_within_chapter(session: Session) -> None:
    """One chapter cannot record two revisions with the same new version."""
    graph = create_story_graph(session)
    session.commit()
    duplicate_revision = Revision(
        chapter_id=graph.chapter.id,
        previous_version=1,
        new_version=2,
        reason="Duplicate version number.",
        score_before=72,
        score_after=77,
        accepted=False,
    )
    session.add(duplicate_revision)

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
