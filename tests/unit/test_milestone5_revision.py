"""Deterministic Milestone 5 revision components."""

from datetime import UTC, datetime

import pytest

from storyforge.agents import RevisionAgent
from storyforge.enums import ConflictSeverity, WorkflowRunStatus
from storyforge.exceptions import AgentExecutionError, InvalidStateError
from storyforge.llm import MockFailure, MockLLMProvider
from storyforge.m5_demo import build_m5_provider
from storyforge.models import WorkflowRun
from storyforge.prompts import build_prompt_registry
from storyforge.revision import (
    AcceptanceEvaluator,
    EvaluationSnapshot,
    RevisedChapterDraft,
    RevisionAgentRequest,
    RevisionBrief,
    RevisionBriefBuilder,
    RevisionBriefConfig,
    RevisionInstruction,
    RevisionIssue,
)
from storyforge.workflows.transitions import redact_error, transition_workflow


def _issue(
    code: str,
    severity: ConflictSeverity,
    category: str,
    source: str = "critic",
) -> RevisionIssue:
    return RevisionIssue(
        code=code,
        category=category,
        severity=severity,
        problem=f"Problem {code}",
        evidence="short evidence",
        suggestion=f"Fix {code}",
        source=source,
    )


def _brief(*, high_code: str = "HIGH") -> RevisionBrief:
    return RevisionBrief(
        chapter_id=1,
        source_version_id=1,
        revision_attempt=1,
        objective="Repair the chapter.",
        instructions=[
            RevisionInstruction(
                priority=1,
                code=high_code,
                category="consistency",
                severity=ConflictSeverity.HIGH,
                problem="A blocking problem.",
                required_change="Remove the contradiction.",
                acceptance_criteria=[f"Resolve issue {high_code}"],
            )
        ],
        global_constraints=["Do not read future information."],
        must_preserve_facts=["Mara | carries | brass key"],
        forbidden_changes=["mentor identity"],
        target_word_range=(240, 360),
        strategy="targeted_repair",
    )


def _snapshot(
    version: int,
    score: float,
    *,
    consistency: float = 7,
    outline: float = 7,
    critical: int = 0,
    high: int = 0,
    blockers: list[str] | None = None,
    issues: list[str] | None = None,
    passed: bool = False,
) -> EvaluationSnapshot:
    return EvaluationSnapshot(
        evaluation_id=version,
        version_id=version,
        final_score=score,
        consistency_score=consistency,
        outline_adherence_score=outline,
        critical_conflicts=critical,
        high_conflicts=high,
        blocking_reasons=blockers or [],
        issue_codes=issues or [],
        passed=passed,
        recommended_action="accept" if passed else "revise",
    )


def test_revision_brief_prioritizes_severity_limits_and_preserves_facts() -> None:
    builder = RevisionBriefBuilder(RevisionBriefConfig(max_instructions=3))
    issues = [
        _issue("LOW_PROSE", ConflictSeverity.LOW, "prose"),
        _issue("HIGH_PLOT", ConflictSeverity.HIGH, "plot"),
        _issue("CRITICAL_STATE", ConflictSeverity.CRITICAL, "consistency", "consistency"),
        _issue("HIGH_OUTLINE", ConflictSeverity.HIGH, "outline"),
        _issue("MEDIUM_PACING", ConflictSeverity.MEDIUM, "pacing"),
    ]

    brief = builder.build(
        chapter_id=1,
        source_version_id=2,
        revision_attempt=1,
        objective="Restore the archive event.",
        issues=issues,
        must_preserve_facts=["Mara | carries | brass key"],
        forbidden_changes=["mentor identity"],
        target_words=300,
    )

    assert [item.code for item in brief.instructions] == [
        "CRITICAL_STATE",
        "HIGH_OUTLINE",
        "HIGH_PLOT",
    ]
    assert brief.must_preserve_facts == ["Mara | carries | brass key"]
    assert brief.forbidden_changes == ["mentor identity"]
    assert brief.target_word_range == (240, 360)


def test_revision_brief_is_deterministic_and_switches_strategy_after_no_improvement() -> None:
    builder = RevisionBriefBuilder()
    arguments = dict(
        chapter_id=1,
        source_version_id=2,
        revision_attempt=2,
        objective="Repair.",
        issues=[
            _issue("B", ConflictSeverity.HIGH, "plot"),
            _issue("A", ConflictSeverity.HIGH, "plot"),
        ],
        must_preserve_facts=[],
        forbidden_changes=[],
        target_words=300,
        previous_improved=False,
    )
    first = builder.build(**arguments)
    second = builder.build(**arguments)
    assert first == second
    assert first.strategy == "structural_rewrite"
    assert [item.code for item in first.instructions] == ["A", "B"]


def test_revision_brief_with_no_issues_is_explicitly_empty() -> None:
    brief = RevisionBriefBuilder().build(
        chapter_id=1,
        source_version_id=1,
        revision_attempt=1,
        objective="Preserve the accepted chapter.",
        issues=[],
        must_preserve_facts=[],
        forbidden_changes=[],
        target_words=300,
    )
    assert brief.instructions == []
    assert brief.strategy == "targeted_repair"


@pytest.mark.parametrize(
    ("new", "attempt", "limit", "decision"),
    [
        (_snapshot(2, 8.2, passed=True), 1, 2, "accept_new"),
        (_snapshot(2, 7.4, blockers=["consistency_low"]), 1, 2, "keep_old_retry"),
        (_snapshot(2, 5.0), 1, 2, "keep_old_retry"),
        (_snapshot(2, 6.5), 2, 2, "human_review"),
        (_snapshot(2, 8.5, critical=1, passed=True), 1, 2, "keep_old_stop"),
    ],
)
def test_acceptance_evaluator_decision_paths(
    new: EvaluationSnapshot,
    attempt: int,
    limit: int,
    decision: str,
) -> None:
    result = AcceptanceEvaluator().compare(
        _snapshot(1, 6.0, issues=["HIGH"]),
        new,
        _brief(),
        revision_attempt=attempt,
        max_revision_attempts=limit,
    )
    assert result.decision == decision
    assert 0 <= result.confidence <= 1
    assert {item.name for item in result.dimensions} == {
        "final_score",
        "consistency",
        "outline_adherence",
    }


def test_acceptance_does_not_accept_unresolved_high_priority_instruction() -> None:
    result = AcceptanceEvaluator().compare(
        _snapshot(1, 6, issues=["HIGH"]),
        _snapshot(2, 8.5, issues=["HIGH"], passed=True),
        _brief(),
        revision_attempt=1,
        max_revision_attempts=2,
    )
    assert result.decision == "keep_old_retry"
    assert result.unresolved_issue_codes == ["HIGH"]


def test_revision_agent_structured_output_and_prompt_versions() -> None:
    provider = build_m5_provider("improve")
    request = RevisionAgentRequest(
        chapter_id=1,
        source_version_id=1,
        original_title="Old",
        original_content="A complete old chapter.",
        original_summary="Old summary.",
        outline={"objective": "Find the key"},
        accepted_facts=["Mara | carries | brass key"],
        brief=_brief(),
    )
    result = RevisionAgent(provider, build_prompt_registry()).revise(request)
    assert isinstance(result.output, RevisedChapterDraft)
    assert result.output.changes_made
    assert result.prompt_versions == {"revision.system": "v1", "revision.user": "v1"}
    assert provider.requests[-1].prompt.name == "revision"


def test_revision_agent_rejects_empty_source_and_converts_provider_error() -> None:
    output = RevisedChapterDraft(
        title="Revised",
        content="Revised body.",
        summary="Summary.",
        changes_made=["Changed structure."],
    )
    provider = MockLLMProvider({RevisedChapterDraft: output}, failures=[MockFailure.TIMEOUT])
    agent = RevisionAgent(provider, build_prompt_registry())
    request = RevisionAgentRequest(
        chapter_id=1,
        source_version_id=1,
        original_title="Old",
        original_content="Old body.",
        original_summary="Old summary.",
        outline={},
        brief=_brief(),
    )
    with pytest.raises(AgentExecutionError):
        agent.revise(request)
    with pytest.raises(ValueError, match="non-empty"):
        agent.revise(request.model_copy(update={"original_content": ""}))


def test_revision_agent_enforces_preserve_and_forbidden_anchors() -> None:
    missing_fact = RevisedChapterDraft(
        title="Revised",
        content="Mara leaves the archive without the evidence.",
        summary="The evidence is missing.",
        changes_made=["Changed the ending."],
    )
    request = RevisionAgentRequest(
        chapter_id=1,
        source_version_id=1,
        original_title="Old",
        original_content="Mara documented the archive.",
        original_summary="Old summary.",
        outline={},
        brief=_brief(),
    )
    with pytest.raises(ValueError, match="must-preserve"):
        RevisionAgent(
            MockLLMProvider({RevisedChapterDraft: missing_fact}), build_prompt_registry()
        ).revise(request)

    forbidden = missing_fact.model_copy(
        update={"content": "Mara carries the brass key and reveals the mentor identity."}
    )
    with pytest.raises(ValueError, match="forbidden"):
        RevisionAgent(
            MockLLMProvider({RevisedChapterDraft: forbidden}), build_prompt_registry()
        ).revise(request)


def test_workflow_transitions_and_error_redaction_are_centralized() -> None:
    run = WorkflowRun(
        project_id=1,
        chapter_id=1,
        current_node="initialize",
        status=WorkflowRunStatus.PENDING,
        started_at=datetime.now(UTC),
    )
    transition_workflow(run, WorkflowRunStatus.RUNNING)
    transition_workflow(run, WorkflowRunStatus.PAUSED)
    with pytest.raises(InvalidStateError):
        transition_workflow(run, WorkflowRunStatus.COMPLETED)
    redacted = redact_error("api_key=sk-secret Authorization: Bearer abc.def password=hunter2")
    assert "sk-secret" not in redacted
    assert "abc.def" not in redacted
    assert "hunter2" not in redacted
