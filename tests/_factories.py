"""Small deterministic factories for persistence tests."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from storyforge.consistency.normalizer import FactNormalizer
from storyforge.enums import (
    ChapterStatus,
    ChapterVersionStatus,
    ForeshadowingStatus,
    WorkflowRunStatus,
)
from storyforge.models import (
    Chapter,
    ChapterVersion,
    Character,
    Evaluation,
    Fact,
    Foreshadowing,
    Location,
    Project,
    Revision,
    StoryRule,
    WorkflowRun,
)


@dataclass(frozen=True)
class StoryGraph:
    """References to a fully populated minimal project graph."""

    project: Project
    chapter: Chapter
    chapter_version: ChapterVersion
    character: Character
    location: Location
    story_rule: StoryRule
    fact: Fact
    foreshadowing: Foreshadowing
    evaluation: Evaluation
    revision: Revision
    workflow_run: WorkflowRun


def make_project(*, title: str = "The Clockwork Harbor") -> Project:
    """Build a valid project without persisting it."""
    return Project(
        title=title,
        genre="Fantasy",
        premise="A cartographer discovers a harbor that moves every midnight.",
        target_chapters=12,
        target_words_per_chapter=2500,
    )


def make_chapter(project_id: int, *, chapter_number: int = 1) -> Chapter:
    """Build a valid chapter without persisting it."""
    return Chapter(
        project_id=project_id,
        chapter_number=chapter_number,
        title=f"Chapter {chapter_number}",
        outline="The harbor moves and the protagonist follows.",
        content="The bells rang at midnight.",
        summary="The moving harbor is revealed.",
        status=ChapterStatus.DRAFT,
        version=1,
        score=72.0,
    )


def create_story_graph(session: Session) -> StoryGraph:
    """Persist one valid instance of every Milestone 1 entity."""
    project = make_project()
    session.add(project)
    session.flush()

    chapter = make_chapter(project.id)
    session.add(chapter)
    session.flush()
    chapter_version = ChapterVersion(
        chapter_id=chapter.id,
        version=1,
        title=chapter.title,
        content=chapter.content,
        summary=chapter.summary or "",
        status=ChapterVersionStatus.ACCEPTED,
        source="test",
        word_count=6,
        provider="test",
        model="test",
    )
    session.add(chapter_version)
    session.flush()
    chapter.current_version_id = chapter_version.id
    chapter.accepted_version_id = chapter_version.id

    character = Character(
        project_id=project.id,
        name="Mara Vale",
        role="protagonist",
        description="A meticulous cartographer.",
        goals=["Map the harbor"],
        personality="Patient and skeptical.",
        speech_style="Precise and restrained.",
        current_state="Following the midnight tide.",
        secrets=["Her compass points to memories"],
    )
    location = Location(
        project_id=project.id,
        name="Clockwork Harbor",
        description="A harbor assembled from brass islands.",
        rules=["It moves at midnight"],
    )
    story_rule = StoryRule(
        project_id=project.id,
        category="world",
        statement="The harbor never occupies the same bay twice.",
        source="initial plan",
        active=True,
    )
    fact = Fact(
        project_id=project.id,
        chapter_id=chapter.id,
        chapter_version_id=chapter_version.id,
        normalized_hash=FactNormalizer().identity_hash("Clockwork Harbor", "moves_at", "midnight"),
        subject="Clockwork Harbor",
        predicate="moves_at",
        object="midnight",
        valid_from_chapter=1,
        valid_to_chapter=None,
        confidence=0.95,
        source_quote="At midnight, the entire harbor began to turn.",
    )
    foreshadowing = Foreshadowing(
        project_id=project.id,
        setup_chapter=1,
        expected_payoff_chapter=5,
        description="Mara's compass points inland.",
        status=ForeshadowingStatus.OPEN,
        payoff_chapter=None,
    )
    evaluation = Evaluation(
        project_id=project.id,
        chapter_id=chapter.id,
        chapter_version_id=chapter_version.id,
        evaluator="test-critic",
        overall_score=78,
        consistency_score=90,
        prose_score=75,
        character_score=76,
        plot_score=73,
        issues=[{"code": "pacing", "message": "Opening is slightly slow"}],
        suggestions=["Tighten the opening paragraph"],
    )
    revision = Revision(
        chapter_id=chapter.id,
        previous_version=1,
        new_version=2,
        reason="Tighten the opening.",
        score_before=72,
        score_after=78,
        accepted=True,
    )
    workflow_run = WorkflowRun(
        project_id=project.id,
        chapter_id=chapter.id,
        current_node="evaluate_chapter",
        status=WorkflowRunStatus.SUCCEEDED,
        retry_count=1,
        error_message=None,
    )
    session.add_all(
        [
            character,
            location,
            story_rule,
            fact,
            foreshadowing,
            evaluation,
            revision,
            workflow_run,
        ]
    )
    session.flush()
    return StoryGraph(
        project=project,
        chapter=chapter,
        chapter_version=chapter_version,
        character=character,
        location=location,
        story_rule=story_rule,
        fact=fact,
        foreshadowing=foreshadowing,
        evaluation=evaluation,
        revision=revision,
        workflow_run=workflow_run,
    )
