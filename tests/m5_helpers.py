"""Shared Milestone 5 integration setup without network or API keys."""

from pathlib import Path

from sqlalchemy import Engine

from storyforge.agents import (
    CriticAgent,
    FactExtractorAgent,
    PlannerAgent,
    RevisionAgent,
    WriterAgent,
)
from storyforge.consistency import ConsistencyChecker
from storyforge.database import SessionFactory, create_session_factory
from storyforge.evaluation import EvaluationScorer, MechanicalEvaluator
from storyforge.llm import MockLLMProvider
from storyforge.m5_demo import build_m5_provider
from storyforge.models import Project
from storyforge.prompts import build_prompt_registry
from storyforge.revision import AcceptanceEvaluator, RevisionBriefBuilder
from storyforge.schemas.domain import ProjectCreate
from storyforge.services import (
    ChapterVersionService,
    ChapterWorkflowService,
    ContextBuilder,
    EvaluationService,
    PlanningService,
    ProjectService,
)


def build_workflow_fixture(
    engine: Engine,
    checkpoint_path: Path,
    scenario: str,
) -> tuple[SessionFactory, Project, MockLLMProvider, ChapterWorkflowService]:
    """Create a planned project and fully injected durable workflow service."""
    factory = create_session_factory(engine)
    provider = build_m5_provider(scenario)
    registry = build_prompt_registry()
    project = ProjectService(factory).create(
        ProjectCreate(
            title=f"M5 {scenario}",
            genre="mystery",
            premise="An archivist investigates a sealed tidal records network.",
            target_chapters=3,
            target_words_per_chapter=300,
        )
    )
    PlanningService(factory, PlannerAgent(provider, registry)).plan_project(project.id)
    versions = ChapterVersionService(
        factory,
        ContextBuilder(factory),
        WriterAgent(provider, registry),
        FactExtractorAgent(provider, registry),
        RevisionAgent(provider, registry),
        RevisionBriefBuilder(),
        AcceptanceEvaluator(),
    )
    evaluations = EvaluationService(
        factory,
        MechanicalEvaluator(),
        ConsistencyChecker(),
        CriticAgent(provider, registry),
        EvaluationScorer(),
    )
    return (
        factory,
        project,
        provider,
        ChapterWorkflowService(factory, versions, evaluations, checkpoint_path),
    )
