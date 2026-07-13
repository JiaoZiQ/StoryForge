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

from storyforge.agents import CriticAgent, FactExtractorAgent, PlannerAgent, WriterAgent
from storyforge.consistency import ConsistencyChecker
from storyforge.database import create_database_engine, create_session_factory
from storyforge.demo import (
    build_conflict_generation_provider,
    build_critic_provider,
    build_demo_provider,
)
from storyforge.enums import ConflictSeverity, ConflictStatus, ConflictType
from storyforge.evaluation import EvaluationScorer, MechanicalEvaluator
from storyforge.evaluation.models import ChapterEvaluationRequest
from storyforge.exceptions import StoryForgeError
from storyforge.models import Conflict, Evaluation, EvaluationIssue, Fact
from storyforge.prompts import build_prompt_registry
from storyforge.repositories import ChapterRepository, ProjectRepository
from storyforge.schemas.context import ContextBuildRequest
from storyforge.schemas.domain import ProjectCreate
from storyforge.schemas.generation import ChapterGenerationRequest
from storyforge.services import (
    ChapterGenerationService,
    ContextBuilder,
    EvaluationService,
    PlanningService,
    ProjectService,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


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
    plan.add_argument("--project-id", type=int, required=True)
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

    demo = commands.add_parser("demo-m3", help="Run the complete offline M3 path")
    demo.add_argument("--database", default="storyforge-m3-demo.sqlite3")
    demo.add_argument("--reset", action="store_true")
    demo.set_defaults(handler=_demo)

    demo_m4 = commands.add_parser("demo-m4", help="Run the complete offline M4 path")
    demo_m4.add_argument("--database", default="storyforge-m4-demo.sqlite3")
    demo_m4.add_argument("--reset", action="store_true")
    demo_m4.set_defaults(handler=_demo_m4)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one CLI command and return a process exit code."""
    args = _parser().parse_args(argv)
    try:
        payload = args.handler(args)
    except (StoryForgeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    _print(payload)
    return 0
