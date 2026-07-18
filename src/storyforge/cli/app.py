"""Offline-first command line interface for StoryForge milestones."""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from storyforge.agents import (
    CriticAgent,
    FactExtractorAgent,
    PlannerAgent,
    RevisionAgent,
    WriterAgent,
)
from storyforge.cli.m6 import configure_demo_m6_alias, configure_m6_commands
from storyforge.cli.m7 import configure_m7_commands
from storyforge.cli.m8 import configure_m8_commands
from storyforge.cli.m9 import configure_m9_commands
from storyforge.cli.m10 import configure_m10_commands
from storyforge.consistency import ConsistencyChecker
from storyforge.database import create_database_engine, create_session_factory
from storyforge.demo import (
    build_conflict_generation_provider,
    build_critic_provider,
    build_demo_critique,
    build_demo_provider,
)
from storyforge.enums import ConflictSeverity, ConflictStatus, ConflictType, FactStatus
from storyforge.evaluation import EvaluationScorer, MechanicalEvaluator
from storyforge.evaluation.models import ChapterCritique, ChapterEvaluationRequest
from storyforge.exceptions import (
    AgentExecutionError,
    ChapterGenerationError,
    ConfigurationError,
    EntityNotFoundError,
    EvaluationError,
    InvalidStateError,
    StoryForgeError,
    WorkflowExecutionError,
)
from storyforge.llm.exceptions import LLMError
from storyforge.m5_demo import build_m5_provider
from storyforge.models import (
    ChapterVersion,
    Conflict,
    Evaluation,
    EvaluationIssue,
    Fact,
    VersionComparison,
    WorkflowEvent,
    WorkflowRun,
)
from storyforge.prompts import build_prompt_registry
from storyforge.repositories import (
    ChapterRepository,
    ChapterVersionRepository,
    ProjectRepository,
)
from storyforge.revision import AcceptanceEvaluator, RevisionBriefBuilder
from storyforge.schemas.context import ContextBuildRequest
from storyforge.schemas.domain import ProjectCreate
from storyforge.schemas.generation import ChapterGenerationRequest
from storyforge.services import (
    ChapterGenerationService,
    ChapterVersionService,
    ChapterWorkflowService,
    ContextBuilder,
    EvaluationService,
    PlanningService,
    ProjectService,
)
from storyforge.workflows import ChapterWorkflowRequest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_GROUPED_COMMANDS = {
    "project",
    "plan",
    "chapter",
    "evaluation",
    "conflict",
    "fact",
    "workflow",
    "demo",
    "demo-m6",
    "demo-m7",
    "demo-m8",
    "demo-m9",
    "memory",
    "retrieval",
    "graph",
    "provider",
    "usage",
    "budget",
    "model-profile",
    "privacy-policy",
    "demo-m10",
}


def _database_url(database: str) -> str:
    path = Path(database).expanduser().resolve()
    return f"sqlite:///{path.as_posix()}"


def _upgrade_database(database_url: str) -> None:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _runtime(database: str) -> tuple[Any, Any]:
    database_url = _database_url(database)
    _upgrade_database(database_url)
    engine = create_database_engine(database_url)
    return engine, create_session_factory(engine)


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _project_target(session_factory: Any, project_id: int) -> int:
    with session_factory() as session:
        project = ProjectRepository(session).get(project_id)
        if project is None:
            raise StoryForgeError(f"Project {project_id} was not found")
        return project.target_chapters


def _create_project(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        project = ProjectService(session_factory).create(
            ProjectCreate(
                title=args.title,
                genre=args.genre,
                premise=args.premise,
                target_chapters=args.chapters,
                target_words_per_chapter=args.words,
            )
        )
        return {"project_id": project.id, "status": project.status, "database": args.database}
    finally:
        engine.dispose()


def _plan(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        target = _project_target(session_factory, args.project_id)
        provider = build_demo_provider(target)
        plan = PlanningService(
            session_factory,
            PlannerAgent(provider, build_prompt_registry()),
        ).plan_project(args.project_id, replace_existing=args.replace_existing)
        return {
            "project_id": args.project_id,
            "status": "planned",
            "chapters": len(plan.chapter_plans),
            "characters": len(plan.characters),
            "locations": len(plan.locations),
        }
    finally:
        engine.dispose()


def _generation_service(session_factory: Any, project_id: int, chapter_number: int) -> Any:
    target = _project_target(session_factory, project_id)
    provider = build_demo_provider(target, chapter_number)
    registry = build_prompt_registry()
    return ChapterGenerationService(
        session_factory,
        ContextBuilder(session_factory),
        WriterAgent(provider, registry),
        FactExtractorAgent(provider, registry),
    )


def _evaluation_service(session_factory: Any, scenario: str = "normal") -> EvaluationService:
    provider = build_critic_provider(scenario)
    return EvaluationService(
        session_factory,
        MechanicalEvaluator(),
        ConsistencyChecker(),
        CriticAgent(provider, build_prompt_registry()),
        EvaluationScorer(),
    )


def _checkpoint_path(database: str, configured: str | None) -> Path:
    if configured:
        return Path(configured).expanduser().resolve()
    database_path = Path(database).expanduser().resolve()
    return database_path.with_name(f"{database_path.stem}.checkpoints.sqlite3")


def _workflow_provider(
    session_factory: Any,
    scenario: str,
    *,
    workflow_run_id: int | None = None,
) -> Any:
    provider = build_m5_provider(scenario)
    if workflow_run_id is not None and scenario == "improve":
        with session_factory() as session:
            completed_critiques = (
                session.scalar(
                    select(func.count(Evaluation.id)).where(
                        Evaluation.workflow_run_id == workflow_run_id
                    )
                )
                or 0
            )
        if completed_critiques:
            provider.register_response(ChapterCritique, build_demo_critique("normal"))
    return provider


def _workflow_service(
    session_factory: Any,
    provider: Any,
    checkpoint_path: Path,
) -> ChapterWorkflowService:
    registry = build_prompt_registry()
    version_service = ChapterVersionService(
        session_factory,
        ContextBuilder(session_factory),
        WriterAgent(provider, registry),
        FactExtractorAgent(provider, registry),
        RevisionAgent(provider, registry),
        RevisionBriefBuilder(),
        AcceptanceEvaluator(),
    )
    evaluation_service = EvaluationService(
        session_factory,
        MechanicalEvaluator(),
        ConsistencyChecker(),
        CriticAgent(provider, registry),
        EvaluationScorer(),
    )
    return ChapterWorkflowService(
        session_factory,
        version_service,
        evaluation_service,
        checkpoint_path,
    )


def _generate(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        result = _generation_service(
            session_factory, args.project_id, args.chapter_number
        ).generate(
            ChapterGenerationRequest(
                project_id=args.project_id,
                chapter_number=args.chapter_number,
                regenerate=args.regenerate,
                max_context_chars=args.max_context_chars,
            )
        )
        return cast(dict[str, object], result.model_dump(mode="json"))
    finally:
        engine.dispose()


def _show_context(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        context = ContextBuilder(session_factory).build(
            ContextBuildRequest(
                project_id=args.project_id,
                chapter_number=args.chapter_number,
                max_context_chars=args.max_context_chars,
            )
        )
        return context.model_dump(mode="json")
    finally:
        engine.dispose()


def _show_chapter(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        with session_factory() as session:
            chapter = ChapterRepository(session).get_by_number(args.project_id, args.chapter_number)
            if chapter is None:
                raise StoryForgeError("Chapter was not found")
            return {
                "project_id": chapter.project_id,
                "chapter_id": chapter.id,
                "chapter_number": chapter.chapter_number,
                "version": chapter.version,
                "status": chapter.status,
                "title": chapter.title,
                "summary": chapter.summary,
                "content": chapter.content,
                "facts": len(chapter.facts),
                "versions": len(chapter.versions),
                "generation_metadata": chapter.generation_metadata,
            }
    finally:
        engine.dispose()


def _evaluate_chapter(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        result = _evaluation_service(session_factory, args.scenario).evaluate(
            ChapterEvaluationRequest(
                project_id=args.project_id,
                chapter_number=args.chapter_number,
            )
        )
        return cast(dict[str, object], result.model_dump(mode="json"))
    finally:
        engine.dispose()


def _show_evaluation(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        history = _evaluation_service(session_factory).list_evaluations(
            args.project_id, args.chapter_number
        )
        if args.evaluation_id is not None:
            history = [item for item in history if item.evaluation_id == args.evaluation_id]
            if not history:
                raise StoryForgeError("Evaluation was not found")
        elif args.latest and history:
            history = [history[-1]]
        return {
            "project_id": args.project_id,
            "chapter_number": args.chapter_number,
            "evaluations": [item.model_dump(mode="json") for item in history],
        }
    finally:
        engine.dispose()


def _list_conflicts(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        severity = ConflictSeverity(args.severity) if args.severity else None
        conflict_type = ConflictType(args.conflict_type) if args.conflict_type else None
        status = ConflictStatus(args.status) if args.status else None
        conflicts = _evaluation_service(session_factory).list_conflicts(
            args.project_id,
            chapter_number=args.chapter_number,
            severity=severity,
            conflict_type=conflict_type,
            status=status,
        )
        return {
            "project_id": args.project_id,
            "count": len(conflicts),
            "conflicts": [_conflict_payload(item) for item in conflicts],
        }
    finally:
        engine.dispose()


def _update_conflict(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        conflict = _evaluation_service(session_factory).update_conflict_status(
            args.project_id,
            args.conflict_id,
            ConflictStatus(args.status),
        )
        return _conflict_payload(conflict)
    finally:
        engine.dispose()


def _conflict_payload(conflict: Conflict) -> dict[str, object]:
    return {
        "id": conflict.id,
        "evaluation_id": conflict.evaluation_id,
        "project_id": conflict.project_id,
        "chapter_id": conflict.chapter_id,
        "type": conflict.conflict_type,
        "severity": conflict.severity,
        "subject": conflict.subject,
        "description": conflict.description,
        "rule_code": conflict.rule_code,
        "status": conflict.status,
        "confidence": conflict.confidence,
        "suggested_resolution": conflict.suggested_resolution,
        "resolved_at": conflict.resolved_at,
    }


def _run_workflow(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        provider = _workflow_provider(session_factory, args.scenario)
        result = _workflow_service(
            session_factory,
            provider,
            _checkpoint_path(args.database, args.checkpoint),
        ).run(
            ChapterWorkflowRequest(
                project_id=args.project_id,
                chapter_number=args.chapter_number,
                operation=args.operation,
                max_revision_attempts=args.max_revision_attempts,
                pause_after=args.pause_after,
            )
        )
        return cast(dict[str, object], result.model_dump(mode="json"))
    finally:
        engine.dispose()


def _resume_workflow(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        provider = _workflow_provider(
            session_factory,
            args.scenario,
            workflow_run_id=args.workflow_run_id,
        )
        result = _workflow_service(
            session_factory,
            provider,
            _checkpoint_path(args.database, args.checkpoint),
        ).resume(args.workflow_run_id)
        return cast(dict[str, object], result.model_dump(mode="json"))
    finally:
        engine.dispose()


def _workflow_status(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        provider = _workflow_provider(session_factory, "pass")
        result = _workflow_service(
            session_factory,
            provider,
            _checkpoint_path(args.database, args.checkpoint),
        ).get_status(args.workflow_run_id)
        return cast(dict[str, object], result.model_dump(mode="json"))
    finally:
        engine.dispose()


def _cancel_workflow(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        provider = _workflow_provider(session_factory, "pass")
        result = _workflow_service(
            session_factory,
            provider,
            _checkpoint_path(args.database, args.checkpoint),
        ).cancel(args.workflow_run_id)
        return cast(dict[str, object], result.model_dump(mode="json"))
    finally:
        engine.dispose()


def _workflow_history(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        provider = _workflow_provider(session_factory, "pass")
        events = _workflow_service(
            session_factory,
            provider,
            _checkpoint_path(args.database, args.checkpoint),
        ).history(args.workflow_run_id)
        return {
            "workflow_run_id": args.workflow_run_id,
            "events": [_workflow_event_payload(item) for item in events],
        }
    finally:
        engine.dispose()


def _workflow_event_payload(event: WorkflowEvent) -> dict[str, object]:
    return {
        "id": event.id,
        "node": event.node,
        "event_type": event.event_type,
        "attempt": event.attempt,
        "status": event.status,
        "duration_ms": event.duration_ms,
        "version_id": event.version_id,
        "evaluation_id": event.evaluation_id,
        "error_code": event.error_code,
        "created_at": event.created_at,
    }


def _show_versions(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        with session_factory() as session:
            chapter = ChapterRepository(session).get_by_number(args.project_id, args.chapter_number)
            if chapter is None:
                raise StoryForgeError("Chapter was not found")
            versions = ChapterVersionRepository(session).list_for_chapter(chapter.id)
            return {
                "project_id": args.project_id,
                "chapter_number": args.chapter_number,
                "current_version_id": chapter.current_version_id,
                "accepted_version_id": chapter.accepted_version_id,
                "versions": [
                    {
                        "id": item.id,
                        "version": item.version,
                        "status": item.status,
                        "source": item.source,
                        "parent_version_id": item.parent_version_id,
                        "workflow_run_id": item.workflow_run_id,
                        "word_count": item.word_count,
                        "provider": item.provider,
                        "model": item.model,
                        "prompt_versions": item.prompt_versions,
                        "created_at": item.created_at,
                        "accepted_at": item.accepted_at,
                    }
                    for item in versions
                ],
            }
    finally:
        engine.dispose()


def _compare_versions(args: argparse.Namespace) -> dict[str, object]:
    engine, session_factory = _runtime(args.database)
    try:
        with session_factory() as session:
            statement = select(VersionComparison).where(
                VersionComparison.workflow_run_id == args.workflow_run_id
            )
            if args.old_version_id is not None:
                statement = statement.where(VersionComparison.old_version_id == args.old_version_id)
            if args.new_version_id is not None:
                statement = statement.where(VersionComparison.new_version_id == args.new_version_id)
            comparisons = list(session.scalars(statement.order_by(VersionComparison.id)))
            return {
                "workflow_run_id": args.workflow_run_id,
                "comparisons": [
                    {
                        "id": item.id,
                        "old_version_id": item.old_version_id,
                        "new_version_id": item.new_version_id,
                        "dimensions": item.dimensions,
                        "overall_delta": item.overall_delta,
                        "resolved_issue_codes": item.resolved_issue_codes,
                        "unresolved_issue_codes": item.unresolved_issue_codes,
                        "newly_introduced_issue_codes": item.newly_introduced_issue_codes,
                        "decision": item.decision,
                        "confidence": item.confidence,
                        "rationale": item.rationale,
                    }
                    for item in comparisons
                ],
            }
    finally:
        engine.dispose()


def _demo(args: argparse.Namespace) -> dict[str, object]:
    database_path = Path(args.database).expanduser().resolve()
    if args.reset and database_path.exists():
        database_path.unlink()
    engine, session_factory = _runtime(str(database_path))
    try:
        project = ProjectService(session_factory).create(
            ProjectCreate(
                title="雾岬潮汐",
                genre="悬疑奇幻",
                premise="一名档案修复师追查随潮汐消失的灯塔。",
                target_chapters=3,
                target_words_per_chapter=1800,
            )
        )
        provider = build_demo_provider(project.target_chapters)
        registry = build_prompt_registry()
        plan = PlanningService(session_factory, PlannerAgent(provider, registry)).plan_project(
            project.id
        )
        context = ContextBuilder(session_factory).build(
            ContextBuildRequest(project_id=project.id, chapter_number=1)
        )
        result = ChapterGenerationService(
            session_factory,
            ContextBuilder(session_factory),
            WriterAgent(provider, registry),
            FactExtractorAgent(provider, registry),
        ).generate(ChapterGenerationRequest(project_id=project.id, chapter_number=1))
        with session_factory() as session:
            persisted = ChapterRepository(session).get_by_number(project.id, 1)
            if persisted is None:
                raise StoryForgeError("Demo chapter was not persisted")
            persisted_project = ProjectRepository(session).get(project.id)
            return {
                "database": str(database_path),
                "project_id": project.id,
                "project_status": persisted_project.status if persisted_project else None,
                "planned_chapters": len(plan.chapter_plans),
                "context": {
                    "estimated_chars": context.budget.estimated_chars,
                    "included_items": context.budget.included_items,
                    "future_chapters_included": False,
                    "author_secrets_included": len(context.author_secrets),
                },
                "chapter": {
                    "id": result.chapter_id,
                    "number": result.chapter_number,
                    "version": result.version,
                    "status": result.status,
                    "summary": result.summary,
                    "content_chars": len(result.content),
                    "facts": len(persisted.facts),
                    "snapshots": len(persisted.versions),
                    "character_updates": result.character_update_count,
                    "foreshadowing_updates": result.foreshadowing_update_count,
                },
                "mock_llm_calls": provider.call_count,
            }
    finally:
        engine.dispose()


def _demo_m4(args: argparse.Namespace) -> dict[str, object]:
    database_path = Path(args.database).expanduser().resolve()
    if args.reset and database_path.exists():
        database_path.unlink()
    engine, session_factory = _runtime(str(database_path))
    try:
        project = ProjectService(session_factory).create(
            ProjectCreate(
                title="雾岬潮汐 - 评估演示",
                genre="悬疑奇幻",
                premise="一名档案修复师追查随潮汐消失的灯塔。",
                target_chapters=3,
                target_words_per_chapter=300,
            )
        )
        registry = build_prompt_registry()
        normal_generation_provider = build_demo_provider(
            project.target_chapters,
            include_canonical_attribute=True,
            include_critical_setup=True,
        )
        PlanningService(
            session_factory,
            PlannerAgent(normal_generation_provider, registry),
        ).plan_project(project.id)
        generation = ChapterGenerationService(
            session_factory,
            ContextBuilder(session_factory),
            WriterAgent(normal_generation_provider, registry),
            FactExtractorAgent(normal_generation_provider, registry),
        )
        generation.generate(ChapterGenerationRequest(project_id=project.id, chapter_number=1))
        normal = _evaluation_service(session_factory, "normal").evaluate(
            ChapterEvaluationRequest(project_id=project.id, chapter_number=1)
        )

        conflict_generation_provider = build_conflict_generation_provider(2)
        ChapterGenerationService(
            session_factory,
            ContextBuilder(session_factory),
            WriterAgent(conflict_generation_provider, registry),
            FactExtractorAgent(conflict_generation_provider, registry),
        ).generate(ChapterGenerationRequest(project_id=project.id, chapter_number=2))
        conflict = _evaluation_service(session_factory, "conflict").evaluate(
            ChapterEvaluationRequest(project_id=project.id, chapter_number=2)
        )

        with session_factory() as session:
            persisted_evaluations = list(
                session.scalars(
                    select(Evaluation)
                    .where(Evaluation.project_id == project.id)
                    .order_by(Evaluation.id)
                )
            )
            database_counts = {
                "evaluations": session.scalar(
                    select(func.count(Evaluation.id)).where(Evaluation.project_id == project.id)
                )
                or 0,
                "evaluation_issues": session.scalar(
                    select(func.count(EvaluationIssue.id))
                    .join(Evaluation, EvaluationIssue.evaluation_id == Evaluation.id)
                    .where(Evaluation.project_id == project.id)
                )
                or 0,
                "conflicts": session.scalar(
                    select(func.count(Conflict.id)).where(Conflict.project_id == project.id)
                )
                or 0,
            }
            future_facts_read = (
                session.scalar(
                    select(func.count(Fact.id)).where(
                        Fact.project_id == project.id,
                        Fact.valid_from_chapter > 2,
                    )
                )
                or 0
            )
        return {
            "database": str(database_path),
            "project_id": project.id,
            "planned_chapters": 3,
            "offline_mock": True,
            "api_key_required": False,
            "Normal chapter evaluation": _demo_evaluation_payload(normal),
            "Conflict chapter evaluation": _demo_evaluation_payload(conflict),
            "database_confirmation": {
                **database_counts,
                "raw_scores_present": all(item.raw_scores for item in persisted_evaluations),
                "weighted_scores_present": all(
                    item.weighted_scores for item in persisted_evaluations
                ),
                "evaluator_versions_present": all(
                    item.evaluator_versions for item in persisted_evaluations
                ),
                "prompt_versions_present": all(
                    item.prompt_versions for item in persisted_evaluations
                ),
            },
            "future_fact_records_after_chapter_2": future_facts_read,
        }
    finally:
        engine.dispose()


def _demo_m5(args: argparse.Namespace) -> dict[str, object]:
    database_path = Path(args.database).expanduser().resolve()
    checkpoint_path = _checkpoint_path(args.database, args.checkpoint)
    if args.reset:
        for path in (database_path, checkpoint_path):
            if path.exists():
                path.unlink()
    engine, session_factory = _runtime(str(database_path))
    try:
        scenario_a = _run_m5_demo_scenario(
            session_factory,
            checkpoint_path,
            title="Milestone 5 - pass",
            scenario="pass",
            max_revision_attempts=2,
        )
        scenario_b = _run_m5_demo_scenario(
            session_factory,
            checkpoint_path,
            title="Milestone 5 - improve",
            scenario="improve",
            max_revision_attempts=2,
        )
        scenario_c = _run_m5_demo_scenario(
            session_factory,
            checkpoint_path,
            title="Milestone 5 - human review",
            scenario="stagnate",
            max_revision_attempts=2,
        )
        recovery = _run_m5_recovery_demo(session_factory, checkpoint_path)
        with session_factory() as session:
            workflow_runs = list(session.scalars(select(WorkflowRun).order_by(WorkflowRun.id)))
            events = list(session.scalars(select(WorkflowEvent).order_by(WorkflowEvent.id)))
            versions = list(session.scalars(select(ChapterVersion).order_by(ChapterVersion.id)))
            evaluations = list(session.scalars(select(Evaluation).order_by(Evaluation.id)))
            conflicts = list(session.scalars(select(Conflict).order_by(Conflict.id)))
            facts = list(session.scalars(select(Fact).order_by(Fact.id)))
            version_keys = [item.idempotency_key for item in versions if item.idempotency_key]
            evaluation_keys = [item.idempotency_key for item in evaluations if item.idempotency_key]
            fact_keys = [(item.chapter_version_id, item.normalized_hash) for item in facts]
            accepted_context = ContextBuilder(session_factory).build(
                ContextBuildRequest(
                    project_id=cast(int, scenario_b["project_id"]), chapter_number=2
                )
            )
            rejected_context = ContextBuilder(session_factory).build(
                ContextBuildRequest(
                    project_id=cast(int, scenario_c["project_id"]), chapter_number=2
                )
            )
        checkpoint_bytes = checkpoint_path.read_bytes() if checkpoint_path.exists() else b""
        return {
            "database": str(database_path),
            "checkpoint": str(checkpoint_path),
            "offline_mock": True,
            "api_key_required": False,
            "network_requests": 0,
            "Scenario A": scenario_a,
            "Scenario B": scenario_b,
            "Scenario C": scenario_c,
            "Checkpoint recovery": recovery,
            "database_confirmation": {
                "workflow_runs": len(workflow_runs),
                "workflow_events": len(events),
                "chapter_versions": len(versions),
                "evaluations": len(evaluations),
                "evaluations_bound_to_versions": all(
                    item.chapter_version_id is not None for item in evaluations
                ),
                "conflicts": len(conflicts),
                "conflicts_bound_to_versions": all(
                    item.chapter_version_id is not None for item in conflicts
                ),
                "resolved_conflicts": sum(
                    item.status is ConflictStatus.RESOLVED for item in conflicts
                ),
                "candidate_or_rejected_facts": sum(
                    item.status is not FactStatus.ACCEPTED for item in facts
                ),
                "accepted_facts": sum(item.status is FactStatus.ACCEPTED for item in facts),
                "accepted_facts_retrievable": len(accepted_context.known_facts),
                "rejected_facts_retrievable": len(rejected_context.known_facts),
                "duplicate_versions": len(version_keys) - len(set(version_keys)),
                "duplicate_evaluations": len(evaluation_keys) - len(set(evaluation_keys)),
                "duplicate_facts": len(fact_keys) - len(set(fact_keys)),
                "future_facts_in_chapter_1_context": len(
                    ContextBuilder(session_factory)
                    .build(
                        ContextBuildRequest(
                            project_id=cast(int, scenario_b["project_id"]),
                            chapter_number=1,
                        )
                    )
                    .known_facts
                ),
                "checkpoint_contains_api_key": b"sk-" in checkpoint_bytes,
                "checkpoint_contains_chapter_body": b"Before sunrise, Mara crossed"
                in checkpoint_bytes,
            },
        }
    finally:
        engine.dispose()


def _run_m5_demo_scenario(
    session_factory: Any,
    checkpoint_path: Path,
    *,
    title: str,
    scenario: str,
    max_revision_attempts: int,
) -> dict[str, object]:
    provider = build_m5_provider(scenario)
    registry = build_prompt_registry()
    project = ProjectService(session_factory).create(
        ProjectCreate(
            title=title,
            genre="mystery",
            premise="An archivist investigates a sealed tidal records network.",
            target_chapters=3,
            target_words_per_chapter=300,
        )
    )
    PlanningService(session_factory, PlannerAgent(provider, registry)).plan_project(project.id)
    status = _workflow_service(session_factory, provider, checkpoint_path).run(
        ChapterWorkflowRequest(
            project_id=project.id,
            chapter_number=1,
            max_revision_attempts=max_revision_attempts,
        )
    )
    with session_factory() as session:
        evaluations = list(
            session.scalars(
                select(Evaluation)
                .where(Evaluation.workflow_run_id == status.workflow_run_id)
                .order_by(Evaluation.id)
            )
        )
        conflict_counts = [len(item.conflicts) for item in evaluations]
    return {
        "project_id": project.id,
        "workflow_run_id": status.workflow_run_id,
        "Workflow status": status.status,
        "Original version": status.original_version,
        "Accepted version": status.accepted_version,
        "Best version": status.best_version,
        "Revision attempts": status.revision_attempt,
        "Score": [item.overall_score for item in evaluations],
        "Conflict count": conflict_counts,
        "Resolved conflicts": (
            max(conflict_counts, default=0) - conflict_counts[-1] if conflict_counts else 0
        ),
        "Final action": ("accept" if status.accepted_version_id is not None else "human_review"),
        "Blocking reasons": status.blocking_reasons,
    }


def _run_m5_recovery_demo(
    session_factory: Any,
    checkpoint_path: Path,
) -> dict[str, object]:
    provider = build_m5_provider("improve")
    registry = build_prompt_registry()
    project = ProjectService(session_factory).create(
        ProjectCreate(
            title="Milestone 5 - checkpoint recovery",
            genre="mystery",
            premise="An archivist resumes a safely checkpointed investigation.",
            target_chapters=3,
            target_words_per_chapter=300,
        )
    )
    PlanningService(session_factory, PlannerAgent(provider, registry)).plan_project(project.id)
    service = _workflow_service(session_factory, provider, checkpoint_path)
    paused = service.run(
        ChapterWorkflowRequest(
            project_id=project.id,
            chapter_number=1,
            max_revision_attempts=2,
            pause_after="evaluate_draft",
        )
    )
    with session_factory() as session:
        before = _workflow_record_counts(session, paused.workflow_run_id)
    completed = service.resume(paused.workflow_run_id)
    with session_factory() as session:
        after = _workflow_record_counts(session, paused.workflow_run_id)
        duplicate_versions = _duplicate_count(
            [
                item.idempotency_key
                for item in session.scalars(
                    select(ChapterVersion).where(
                        ChapterVersion.workflow_run_id == paused.workflow_run_id
                    )
                )
                if item.idempotency_key
            ]
        )
        duplicate_evaluations = _duplicate_count(
            [
                item.idempotency_key
                for item in session.scalars(
                    select(Evaluation).where(Evaluation.workflow_run_id == paused.workflow_run_id)
                )
                if item.idempotency_key
            ]
        )
        fact_keys = [
            (item.chapter_version_id, item.normalized_hash)
            for item in session.scalars(
                select(Fact).where(Fact.workflow_run_id == paused.workflow_run_id)
            )
        ]
    return {
        "Paused after": paused.current_node,
        "Resumed from": paused.current_node,
        "Final status": completed.status,
        "Accepted version": completed.accepted_version,
        "Records before resume": before,
        "Records after resume": after,
        "Duplicate versions": duplicate_versions,
        "Duplicate evaluations": duplicate_evaluations,
        "Duplicate facts": _duplicate_count(fact_keys),
    }


def _workflow_record_counts(session: Any, workflow_run_id: int) -> dict[str, int]:
    return {
        "versions": session.scalar(
            select(func.count(ChapterVersion.id)).where(
                ChapterVersion.workflow_run_id == workflow_run_id
            )
        )
        or 0,
        "evaluations": session.scalar(
            select(func.count(Evaluation.id)).where(Evaluation.workflow_run_id == workflow_run_id)
        )
        or 0,
        "facts": session.scalar(
            select(func.count(Fact.id)).where(Fact.workflow_run_id == workflow_run_id)
        )
        or 0,
    }


def _duplicate_count(items: Sequence[object]) -> int:
    return len(items) - len(set(items))


def _demo_evaluation_payload(result: Any) -> dict[str, object]:
    return {
        "Mechanical score": result.mechanical_score,
        "Critic score": result.critic_score,
        "Consistency score": result.consistency_score,
        "Final score": result.final_score,
        "Passed": result.passed,
        "Issue count": result.issue_count,
        "Conflicts detected": result.conflict_count,
        "Critical conflicts": result.critical_conflict_count,
        "Recommended action": result.recommended_action,
        "Evaluation version": result.evaluation_version,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="storyforge", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-project", help="Create a project")
    create.add_argument("--database", default="storyforge.db")
    create.add_argument("--title", required=True)
    create.add_argument("--genre", required=True)
    create.add_argument("--premise", required=True)
    create.add_argument("--chapters", type=int, required=True)
    create.add_argument("--words", type=int, default=2000)
    create.set_defaults(handler=_create_project)

    plan = commands.add_parser("plan", help="Plan a project with the offline mock")
    plan.add_argument("--database", default="storyforge.db")
    plan.add_argument("--project-id", type=int)
    plan.add_argument("--replace-existing", action="store_true")
    plan.set_defaults(handler=_plan)

    generate = commands.add_parser("generate-chapter", help="Generate one planned chapter")
    generate.add_argument("--database", default="storyforge.db")
    generate.add_argument("--project-id", type=int, required=True)
    generate.add_argument("--chapter-number", type=int, required=True)
    generate.add_argument("--max-context-chars", type=int, default=24_000)
    generate.add_argument("--regenerate", action="store_true")
    generate.set_defaults(handler=_generate)

    context = commands.add_parser("show-context", help="Show the bounded writer context")
    context.add_argument("--database", default="storyforge.db")
    context.add_argument("--project-id", type=int, required=True)
    context.add_argument("--chapter-number", type=int, required=True)
    context.add_argument("--max-context-chars", type=int, default=24_000)
    context.set_defaults(handler=_show_context)

    chapter = commands.add_parser("show-chapter", help="Show a generated chapter")
    chapter.add_argument("--database", default="storyforge.db")
    chapter.add_argument("--project-id", type=int, required=True)
    chapter.add_argument("--chapter-number", type=int, required=True)
    chapter.set_defaults(handler=_show_chapter)

    evaluate = commands.add_parser("evaluate-chapter", help="Evaluate a generated chapter")
    evaluate.add_argument("--database", default="storyforge.db")
    evaluate.add_argument("--project-id", type=int, required=True)
    evaluate.add_argument("--chapter-number", type=int, required=True)
    evaluate.add_argument(
        "--scenario",
        choices=("normal", "death", "outline", "poor", "conflict"),
        default="normal",
        help="Deterministic MockLLM critic scenario",
    )
    evaluate.set_defaults(handler=_evaluate_chapter)

    show_evaluation = commands.add_parser(
        "show-evaluation", help="Show versioned chapter evaluations"
    )
    show_evaluation.add_argument("--database", default="storyforge.db")
    show_evaluation.add_argument("--project-id", type=int, required=True)
    show_evaluation.add_argument("--chapter-number", type=int, required=True)
    show_evaluation.add_argument("--evaluation-id", type=int)
    show_evaluation.add_argument("--latest", action="store_true")
    show_evaluation.set_defaults(handler=_show_evaluation)

    list_conflicts = commands.add_parser(
        "list-conflicts", help="List persisted consistency conflicts"
    )
    list_conflicts.add_argument("--database", default="storyforge.db")
    list_conflicts.add_argument("--project-id", type=int, required=True)
    list_conflicts.add_argument("--chapter-number", type=int)
    list_conflicts.add_argument("--severity", choices=tuple(ConflictSeverity))
    list_conflicts.add_argument("--type", dest="conflict_type", choices=tuple(ConflictType))
    list_conflicts.add_argument("--status", choices=tuple(ConflictStatus))
    list_conflicts.set_defaults(handler=_list_conflicts)

    update_conflict = commands.add_parser(
        "update-conflict", help="Update a persisted conflict status"
    )
    update_conflict.add_argument("--database", default="storyforge.db")
    update_conflict.add_argument("--project-id", type=int, required=True)
    update_conflict.add_argument("--conflict-id", type=int, required=True)
    update_conflict.add_argument("--status", choices=tuple(ConflictStatus), required=True)
    update_conflict.set_defaults(handler=_update_conflict)

    run_workflow = commands.add_parser(
        "run-workflow", help="Run a durable chapter generation and revision workflow"
    )
    run_workflow.add_argument("--database", default="storyforge.db")
    run_workflow.add_argument("--checkpoint")
    run_workflow.add_argument("--project-id", type=int, required=True)
    run_workflow.add_argument("--chapter-number", type=int, required=True)
    run_workflow.add_argument(
        "--operation", choices=("generate", "evaluate_existing"), default="generate"
    )
    run_workflow.add_argument("--max-revision-attempts", type=int, default=2)
    run_workflow.add_argument("--scenario", choices=("pass", "improve", "stagnate"), default="pass")
    run_workflow.add_argument("--pause-after")
    run_workflow.set_defaults(handler=_run_workflow)

    resume_workflow = commands.add_parser(
        "resume-workflow", help="Resume a paused workflow from its checkpoint"
    )
    resume_workflow.add_argument("--database", default="storyforge.db")
    resume_workflow.add_argument("--checkpoint")
    resume_workflow.add_argument("--workflow-run-id", type=int, required=True)
    resume_workflow.add_argument(
        "--scenario", choices=("pass", "improve", "stagnate"), default="pass"
    )
    resume_workflow.set_defaults(handler=_resume_workflow)

    workflow_status = commands.add_parser(
        "workflow-status", help="Show the current workflow projection"
    )
    workflow_status.add_argument("--database", default="storyforge.db")
    workflow_status.add_argument("--checkpoint")
    workflow_status.add_argument("--workflow-run-id", type=int, required=True)
    workflow_status.set_defaults(handler=_workflow_status)

    cancel_workflow = commands.add_parser(
        "cancel-workflow", help="Cancel a paused or running workflow at a node boundary"
    )
    cancel_workflow.add_argument("--database", default="storyforge.db")
    cancel_workflow.add_argument("--checkpoint")
    cancel_workflow.add_argument("--workflow-run-id", type=int, required=True)
    cancel_workflow.set_defaults(handler=_cancel_workflow)

    workflow_history = commands.add_parser(
        "workflow-history", help="Show ordered content-free workflow events"
    )
    workflow_history.add_argument("--database", default="storyforge.db")
    workflow_history.add_argument("--checkpoint")
    workflow_history.add_argument("--workflow-run-id", type=int, required=True)
    workflow_history.set_defaults(handler=_workflow_history)

    show_versions = commands.add_parser(
        "show-versions", help="Show immutable chapter version history"
    )
    show_versions.add_argument("--database", default="storyforge.db")
    show_versions.add_argument("--project-id", type=int, required=True)
    show_versions.add_argument("--chapter-number", type=int, required=True)
    show_versions.set_defaults(handler=_show_versions)

    compare_versions = commands.add_parser(
        "compare-versions", help="Show persisted pairwise version comparisons"
    )
    compare_versions.add_argument("--database", default="storyforge.db")
    compare_versions.add_argument("--workflow-run-id", type=int, required=True)
    compare_versions.add_argument("--old-version-id", type=int)
    compare_versions.add_argument("--new-version-id", type=int)
    compare_versions.set_defaults(handler=_compare_versions)

    demo = commands.add_parser("demo-m3", help="Run the complete offline M3 path")
    demo.add_argument("--database", default="storyforge-m3-demo.sqlite3")
    demo.add_argument("--reset", action="store_true")
    demo.set_defaults(handler=_demo)

    demo_m4 = commands.add_parser("demo-m4", help="Run the complete offline M4 path")
    demo_m4.add_argument("--database", default="storyforge-m4-demo.sqlite3")
    demo_m4.add_argument("--reset", action="store_true")
    demo_m4.set_defaults(handler=_demo_m4)

    demo_m5 = commands.add_parser("demo-m5", help="Run the complete offline M5 workflow")
    demo_m5.add_argument("--database", default="storyforge-m5-demo.sqlite3")
    demo_m5.add_argument("--checkpoint")
    demo_m5.add_argument("--reset", action="store_true")
    demo_m5.set_defaults(handler=_demo_m5)
    configure_m6_commands(commands, plan)
    configure_demo_m6_alias(commands)
    configure_m7_commands(commands)
    configure_m8_commands(commands)
    configure_m9_commands(commands)
    configure_m10_commands(commands)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one CLI command and return a process exit code."""
    args = _parser().parse_args(argv)
    try:
        payload = args.handler(args)
    except EntityNotFoundError as exc:
        _print_cli_error("resource_not_found", str(exc))
        return 3
    except InvalidStateError as exc:
        _print_cli_error("state_conflict", str(exc))
        return 4 if args.command in _GROUPED_COMMANDS else 2
    except (
        AgentExecutionError,
        ChapterGenerationError,
        ConfigurationError,
        EvaluationError,
        WorkflowExecutionError,
        LLMError,
    ):
        _print_cli_error(
            "provider_unavailable", "The configured provider could not complete the operation"
        )
        return 5
    except SQLAlchemyError:
        _print_cli_error("database_error", "The database operation could not be completed")
        return 6
    except (StoryForgeError, ValueError) as exc:
        _print_cli_error("validation_error", str(exc))
        return 2
    except Exception:
        _print_cli_error("internal_error", "An unexpected internal error occurred")
        return 1
    if getattr(args, "output", "json") == "human":
        _print_human(payload)
    else:
        _print(payload)
    return 0


def _print_cli_error(code: str, message: str) -> None:
    print(
        json.dumps({"error": code, "message": message}, ensure_ascii=False),
        file=sys.stderr,
    )


def _print_human(payload: object, *, indent: int = 0) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, dict):
                print(f"{' ' * indent}{key}")
                _print_human(value, indent=indent + 2)
            elif isinstance(value, list):
                print(f"{' ' * indent}{key}: {len(value)} item(s)")
                for item in value:
                    _print_human(item, indent=indent + 2)
            else:
                print(f"{' ' * indent}{key}: {value}")
    elif isinstance(payload, list):
        for item in payload:
            _print_human(item, indent=indent)
    else:
        print(f"{' ' * indent}{payload}")
