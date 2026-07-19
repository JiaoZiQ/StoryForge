"""Deterministic whole-book rule-engine and scoring coverage."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from storyforge.book import (
    BookChapterScheduler,
    BookEvaluationScorer,
    BookRevisionPlanner,
    BookScoringConfig,
    ChapterTransitionAnalyzer,
    CharacterArcAnalyzer,
    ForeshadowingAnalyzer,
    PacingAnalyzer,
    RepetitionDetector,
    TimelineAnalyzer,
)
from storyforge.book.mock import build_mock_book_critique
from storyforge.book.models import (
    AcceptedFactData,
    BookAnalysisBundle,
    BookCriticContext,
    BookIssue,
    CharacterProfileData,
    ForeshadowingItemData,
    SnapshotChapter,
)
from storyforge.enums import BookRunMode
from storyforge.exceptions import DomainValidationError


def _fact(
    fact_id: int,
    chapter: int,
    subject: str,
    predicate: str,
    object_value: str,
    *,
    confidence: float = 0.95,
) -> AcceptedFactData:
    return AcceptedFactData(
        id=fact_id,
        chapter_id=chapter,
        chapter_version_id=chapter * 10,
        chapter_number=chapter,
        subject=subject,
        predicate=predicate,
        object=object_value,
        confidence=confidence,
        evidence=f"evidence {fact_id}",
        valid_from_chapter=chapter,
    )


def _chapter(
    number: int,
    *,
    content: str | None = None,
    score: float = 8.0,
    words: int = 400,
    events: list[str] | None = None,
    characters: list[str] | None = None,
    locations: list[str] | None = None,
) -> SnapshotChapter:
    return SnapshotChapter(
        chapter_id=number,
        chapter_number=number,
        chapter_version_id=number * 10,
        version=1,
        title=f"Chapter {number}",
        summary=f"Distinct summary {number}",
        word_count=words,
        content=content or f"Distinct scene {number} advances its own objective with consequence.",
        evaluation_score=score,
        outline_adherence=8,
        dialogue_ratio=0.25,
        key_events=events or [f"event-{number}"],
        characters_present=characters or ["Mara"],
        locations_present=locations or [f"place-{number}"],
    )


def _analysis(
    chapters: list[SnapshotChapter] | None = None,
    facts: list[AcceptedFactData] | None = None,
) -> BookAnalysisBundle:
    chapter_items = chapters or [_chapter(1), _chapter(2)]
    fact_items = facts or []
    arcs, knowledge, relationships = CharacterArcAnalyzer().analyze(
        chapter_items,
        fact_items,
        [
            CharacterProfileData(
                id=1,
                name="Mara",
                role="protagonist",
                goals=["solve"],
                personality="careful",
                current_state="ready",
            )
        ],
    )
    return BookAnalysisBundle(
        timeline=TimelineAnalyzer().analyze(fact_items),
        character_arcs=arcs,
        knowledge=knowledge,
        relationships=relationships,
        foreshadowing=ForeshadowingAnalyzer().analyze([], final_chapter=len(chapter_items)),
        transitions=ChapterTransitionAnalyzer().analyze(chapter_items),
        pacing=PacingAnalyzer().analyze(chapter_items),
        repetition=RepetitionDetector().analyze(chapter_items),
    )


def test_scheduler_sequential_dependency_and_terminal_paths() -> None:
    scheduler = BookChapterScheduler(concurrency=1)
    first = scheduler.decide(
        mode=BookRunMode.SEQUENTIAL,
        chapter_numbers=[1, 2, 3],
        chapter_status={1: "planned", 2: "planned", 3: "planned"},
    )
    second = scheduler.decide(
        mode=BookRunMode.DEPENDENCY_AWARE,
        chapter_numbers=[1, 2, 3],
        chapter_status={1: "accepted", 2: "planned", 3: "planned"},
        dependencies={1: [], 2: [1], 3: [1]},
    )
    completed = scheduler.decide(
        mode=BookRunMode.SEQUENTIAL,
        chapter_numbers=[1, 2],
        chapter_status={1: "accepted", 2: "accepted"},
    )

    assert first.chapter_number == 1
    assert second.chapter_number == 2
    assert completed.action == "complete"


@pytest.mark.parametrize(
    ("numbers", "dependencies"),
    [([1, 3], None), ([1, 2], {1: [2], 2: [1]})],
)
def test_scheduler_rejects_gaps_and_cycles(
    numbers: list[int], dependencies: dict[int, list[int]] | None
) -> None:
    with pytest.raises(DomainValidationError):
        BookChapterScheduler().validate_plan(numbers, dependencies)


def test_scheduler_cancel_wait_and_needs_review_are_explicit() -> None:
    scheduler = BookChapterScheduler()
    common = {"mode": BookRunMode.SEQUENTIAL, "chapter_numbers": [1, 2]}
    assert scheduler.decide(**common, chapter_status={1: "running", 2: "planned"}).action == "wait"
    assert (
        scheduler.decide(
            **common,
            chapter_status={1: "needs_review", 2: "planned"},
        ).action
        == "human_review"
    )
    assert (
        scheduler.decide(
            **common,
            chapter_status={1: "planned", 2: "planned"},
            cancel_requested=True,
        ).action
        == "cancel"
    )


def test_timeline_detects_death_location_object_and_cause_conflicts() -> None:
    facts = [
        _fact(1, 1, "Mara", "status", "dead"),
        _fact(2, 2, "Mara", "acts", "opens gate"),
        _fact(3, 2, "Mara", "located_at", "Harbor"),
        _fact(4, 2, "Mara", "located_at", "Mountain"),
        _fact(5, 1, "key", "status", "destroyed"),
        _fact(6, 3, "key", "uses", "gate"),
        _fact(7, 3, "storm", "caused_by", "warning"),
        _fact(8, 4, "warning", "occurs", "afterward"),
    ]
    result = TimelineAnalyzer().analyze(facts)
    codes = {item.code for item in result.conflicts}

    assert "timeline.dead_character_action" in codes
    assert "timeline.simultaneous_locations" in codes
    assert "timeline.destroyed_object_reused" in codes
    assert "timeline.cause_after_effect" in codes
    assert 0 <= result.score <= 10


def test_low_confidence_timeline_match_never_becomes_critical() -> None:
    result = TimelineAnalyzer().analyze(
        [
            _fact(1, 1, "Mara", "status", "dead", confidence=0.4),
            _fact(2, 2, "Mara", "acts", "returns", confidence=0.5),
        ]
    )
    assert result.conflicts
    assert all(item.severity != "critical" for item in result.conflicts)


def test_character_arc_builds_knowledge_relationships_and_missing_protagonist_issue() -> None:
    chapters = [
        _chapter(1, characters=["Mara", "Ivo"]),
        _chapter(2, characters=["Ivo"]),
        _chapter(3, characters=["Ivo"]),
        _chapter(4, characters=["Ivo"]),
    ]
    characters = [
        CharacterProfileData(
            id=1,
            name="Mara",
            role="protagonist",
            goals=["solve"],
            personality="careful",
            current_state="ready",
        ),
        CharacterProfileData(
            id=2,
            name="Ivo",
            role="supporting",
            goals=[],
            personality="direct",
            current_state="ready",
        ),
    ]
    facts = [
        _fact(1, 1, "Mara", "knows", "tide secret"),
        _fact(2, 1, "Mara", "trusts", "Ivo"),
    ]
    arcs, knowledge, relationships = CharacterArcAnalyzer().analyze(chapters, facts, characters)

    assert knowledge[0].learned_chapter == 1
    assert relationships[0].relationship_type == "trust"
    assert any(issue.code == "character.protagonist_absent" for issue in arcs.issues)


@pytest.mark.parametrize(
    ("item", "code"),
    [
        (
            ForeshadowingItemData(
                id=1,
                description="clue",
                importance="high",
                setup_chapter=3,
                expected_payoff_chapter=5,
                payoff_chapter=2,
                status="paid_off",
            ),
            "foreshadowing.payoff_before_setup",
        ),
        (
            ForeshadowingItemData(
                id=2,
                description="clue",
                importance="high",
                setup_chapter=1,
                expected_payoff_chapter=3,
                status="open",
            ),
            "foreshadowing.major_unresolved",
        ),
    ],
)
def test_foreshadowing_issues_are_explainable(item: ForeshadowingItemData, code: str) -> None:
    result = ForeshadowingAnalyzer().analyze([item], final_chapter=5)
    assert any(issue.code == code for issue in result.issues)


def test_transitions_pacing_and_repetition_find_bounded_candidates() -> None:
    paragraph = "The same sufficiently long paragraph repeats the brass harbor warning exactly."
    chapters = [
        _chapter(1, content=paragraph, words=500, events=["shared event"]),
        _chapter(2, content=paragraph, words=500, events=["shared event"]),
        _chapter(3, content="Short ending.", words=100, score=4),
    ]
    transitions = ChapterTransitionAnalyzer().analyze(chapters)
    pacing = PacingAnalyzer().analyze(chapters)
    repetition = RepetitionDetector().analyze(chapters)

    assert any(issue.code == "transition.repeated_exposition" for issue in transitions[0].issues)
    assert any(issue.code == "pacing.rushed_ending" for issue in pacing.issues)
    assert repetition.duplicate_paragraphs == 1
    assert all(0 <= result.score <= 10 for result in transitions)


def test_book_critic_context_rejects_unbounded_excerpts() -> None:
    with pytest.raises(ValidationError, match="at most eight"):
        BookCriticContext(
            project_title="Book",
            premise="Premise",
            book_summary="Summary",
            chapter_summaries=[{"chapter": 1, "summary": "s"}],
            timeline_summary={},
            character_arc_summary={},
            relationship_summary=[],
            foreshadowing_summary={},
            pacing_summary={},
            transition_summary={},
            repetition_summary={},
            chapter_score_trend=[8],
            priority_excerpt_summaries=[{"chapter": i} for i in range(9)],
        )


def test_book_scoring_accepts_clean_book_and_caps_critical_book() -> None:
    clean = _analysis()
    scorer = BookEvaluationScorer()
    accepted = scorer.score(
        chapter_scores=[8, 8.5],
        ending_score=8.5,
        analysis=clean,
        critique=build_mock_book_critique(),
    )
    critical_analysis = _analysis(
        facts=[_fact(1, 1, "Mara", "status", "dead"), _fact(2, 2, "Mara", "acts", "runs")]
    )
    critique = build_mock_book_critique().model_copy(
        update={
            "global_issues": [
                BookIssue(
                    code="timeline.dead_character_action",
                    category="timeline",
                    severity="critical",
                    description="Death conflict",
                    chapter_numbers=[1, 2],
                    suggestion="Revise chapter 2",
                )
            ],
            "pass_recommendation": False,
        }
    )
    blocked = scorer.score(
        chapter_scores=[9, 9],
        ending_score=9,
        analysis=critical_analysis,
        critique=critique,
    )

    assert accepted.passed
    assert blocked.final_score <= 5
    assert blocked.recommended_action == "targeted_revision"


def test_book_scoring_config_requires_complete_unit_weights() -> None:
    with pytest.raises(ValidationError, match="sum to one"):
        BookScoringConfig(weights={"chapter_average": 1.0})


def test_revision_planner_prioritizes_critical_and_honors_budget() -> None:
    issues = [
        BookIssue(
            code="style.low",
            category="repetition",
            severity="low",
            description="Style",
            chapter_numbers=[5],
            suggestion="Vary wording",
        ),
        BookIssue(
            code="timeline.critical",
            category="timeline",
            severity="critical",
            description="Timeline",
            chapter_numbers=[2],
            suggestion="Repair chronology",
        ),
    ]
    critique = build_mock_book_critique(passing=False).model_copy(
        update={"global_issues": issues, "pass_recommendation": False}
    )
    evaluation = BookEvaluationScorer().score(
        chapter_scores=[8] * 5,
        ending_score=8,
        analysis=_analysis([_chapter(i) for i in range(1, 6)]),
        critique=critique,
    )
    plan = BookRevisionPlanner(maximum_chapters=3).build(
        snapshot_id=1,
        revision_round=1,
        total_chapters=5,
        evaluation=evaluation,
        critique=critique,
        remaining_calls=1,
        remaining_tokens=12_000,
        remaining_cost=Decimal("1"),
    )

    assert plan.dependency_order == [2]
    assert plan.chapter_tasks[0].affected_future_chapters == [3, 4, 5]
    assert plan.estimated_calls == 1
