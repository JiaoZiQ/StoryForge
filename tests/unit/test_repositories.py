"""Unit tests for transaction-neutral repository CRUD."""

import pytest
from sqlalchemy.orm import Session
from tests._factories import create_story_graph, make_project

from storyforge.repositories import (
    ChapterRepository,
    CharacterRepository,
    EvaluationRepository,
    FactRepository,
    ForeshadowingRepository,
    LocationRepository,
    ProjectRepository,
    RevisionRepository,
    StoryRuleRepository,
    WorkflowRunRepository,
)


def test_project_repository_crud(session: Session) -> None:
    """The generic repository contract should cover create/read/update/delete."""
    repository = ProjectRepository(session)
    project = repository.add(make_project())

    assert project.id > 0
    assert repository.get(project.id) is project
    assert repository.list() == [project]

    updated = repository.update(project, {"title": "Updated Harbor"})
    assert updated.title == "Updated Harbor"

    repository.delete(project)
    assert repository.get(project.id) is None


def test_repositories_cover_each_domain_entity(session: Session) -> None:
    """Every Milestone 1 entity should have a typed repository."""
    graph = create_story_graph(session)

    assert ProjectRepository(session).get(graph.project.id) is graph.project
    assert CharacterRepository(session).list() == [graph.character]
    assert LocationRepository(session).list() == [graph.location]
    assert StoryRuleRepository(session).list() == [graph.story_rule]
    assert ChapterRepository(session).get_by_number(graph.project.id, 1) is graph.chapter
    assert FactRepository(session).list() == [graph.fact]
    assert ForeshadowingRepository(session).list() == [graph.foreshadowing]
    assert EvaluationRepository(session).list() == [graph.evaluation]
    assert RevisionRepository(session).list() == [graph.revision]
    assert WorkflowRunRepository(session).list() == [graph.workflow_run]


def test_repository_rejects_invalid_paging_and_fields(session: Session) -> None:
    """Repository boundaries should reject malformed generic operations."""
    repository = ProjectRepository(session)
    project = repository.add(make_project())

    with pytest.raises(ValueError, match="offset"):
        repository.list(offset=-1)
    with pytest.raises(ValueError, match="limit"):
        repository.list(limit=0)
    with pytest.raises(ValueError, match="immutable"):
        repository.update(project, {"id": 99})
    with pytest.raises(ValueError, match="Unknown"):
        repository.update(project, {"missing": "value"})
    with pytest.raises(ValueError, match="Unknown"):
        repository.update(project, {"chapters": []})
