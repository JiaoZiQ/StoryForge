"""Grouped Milestone 6 CLI commands backed by application services."""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from pydantic import BaseModel
from sqlalchemy import Engine

from storyforge.application import (
    ChapterApplicationService,
    DomainServiceFactory,
    EvaluationApplicationService,
    PlanningApplicationService,
    ProjectApplicationService,
    WorkflowApplicationService,
)
from storyforge.database import SessionFactory, create_database_engine, create_session_factory
from storyforge.enums import ConflictStatus, FactStatus
from storyforge.m6_demo import run_demo_m6
from storyforge.schemas.api import (
    ConflictPatchRequest,
    EvaluateChapterRequest,
    GenerateChapterRequest,
    GeneratePlanRequest,
    ProjectCreateRequest,
    StartWorkflowRequest,
)
from storyforge.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class _Services:
    engine: Engine
    projects: ProjectApplicationService
    planning: PlanningApplicationService
    chapters: ChapterApplicationService
    evaluations: EvaluationApplicationService
    workflows: WorkflowApplicationService


@contextmanager
def _services(args: argparse.Namespace) -> Iterator[_Services]:
    database = Path(args.database).expanduser().resolve()
    database_url = f"sqlite:///{database.as_posix()}"
    _upgrade(database_url)
    configured = Settings.from_env()
    settings = configured.model_copy(
        update={
            "database_url": database_url,
            "mock_workflow_scenario": getattr(args, "scenario", "improve"),
            "mock_critic_scenario": getattr(args, "critic_scenario", "normal"),
            "checkpoint_path": configured.checkpoint_path
            or database.with_name(f"{database.stem}.checkpoints.sqlite3"),
            "allow_debug_pause_nodes": True,
            "enable_http_logging": False,
        }
    )
    engine = create_database_engine(database_url)
    session_factory: SessionFactory = create_session_factory(engine)
    factory = DomainServiceFactory(session_factory, settings)
    try:
        yield _Services(
            engine=engine,
            projects=ProjectApplicationService(session_factory),
            planning=PlanningApplicationService(session_factory, factory),
            chapters=ChapterApplicationService(session_factory, factory, settings),
            evaluations=EvaluationApplicationService(session_factory, factory),
            workflows=WorkflowApplicationService(session_factory, factory, settings),
        )
    finally:
        engine.dispose()


def _upgrade(database_url: str) -> None:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _dump(value: BaseModel) -> dict[str, object]:
    return value.model_dump(mode="json")


def _project_create(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.projects.create(
                ProjectCreateRequest(
                    title=args.title,
                    genre=args.genre,
                    premise=args.premise,
                    target_chapters=args.chapters,
                    target_words_per_chapter=args.words,
                    language=args.language,
                    tone=args.tone,
                    audience=args.audience,
                    additional_requirements=args.additional_requirements,
                )
            )
        )


def _project_list(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.projects.list(page=args.page, page_size=args.page_size, search=args.search)
        )


def _project_show(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(services.projects.get(args.project_id))


def _plan_generate(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.planning.generate(
                args.project_id,
                GeneratePlanRequest(replace_existing=args.replace_existing),
            )
        )


def _plan_show(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(services.planning.get(args.project_id))


def _chapter_list(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.chapters.list_chapters(
                args.project_id, page=args.page, page_size=args.page_size
            )
        )


def _chapter_show(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.chapters.get(
                args.project_id,
                args.chapter_number,
                include_content=args.include_content,
            )
        )


def _chapter_context(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.chapters.context(
                args.project_id,
                args.chapter_number,
                max_context_chars=args.max_context_chars,
            )
        )


def _chapter_generate(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.chapters.generate(
                args.project_id,
                args.chapter_number,
                GenerateChapterRequest(
                    regenerate=args.regenerate,
                    max_context_chars=args.max_context_chars,
                ),
            )
        )


def _chapter_evaluate(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.evaluations.evaluate(
                args.project_id,
                args.chapter_number,
                EvaluateChapterRequest(force_new_version=args.force),
            )
        )


def _chapter_versions(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.chapters.list_versions(
                args.project_id,
                args.chapter_number,
                page=args.page,
                page_size=args.page_size,
            )
        )


def _chapter_diff(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.chapters.diff(
                args.project_id,
                args.chapter_number,
                args.version_id,
                old_version_id=args.old_version_id,
                include_unified_diff=args.include_diff,
            )
        )


def _evaluation_list(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.evaluations.list_evaluations(
                args.project_id,
                args.chapter_number,
                page=args.page,
                page_size=args.page_size,
            )
        )


def _evaluation_show(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.evaluations.get_evaluation(
                args.project_id, args.chapter_number, args.evaluation_id
            )
        )


def _conflict_list(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.evaluations.list_conflicts(
                args.project_id,
                page=args.page,
                page_size=args.page_size,
                chapter_number=args.chapter_number,
            )
        )


def _conflict_resolve(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.evaluations.update_conflict(
                args.project_id,
                args.conflict_id,
                ConflictPatchRequest(
                    status=ConflictStatus.RESOLVED,
                    resolution_note=args.note,
                ),
            )
        )


def _fact_list(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.evaluations.list_facts(
                args.project_id,
                page=args.page,
                page_size=args.page_size,
                chapter_number=args.chapter_number,
                status=FactStatus.ACCEPTED,
                valid_at_chapter=args.valid_at_chapter,
            )
        )


def _workflow_run(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.workflows.start(
                args.project_id,
                args.chapter_number,
                StartWorkflowRequest(
                    max_revision_attempts=args.max_revision_attempts,
                    pause_after_node=args.pause_after_node,
                ),
            )
        )


def _workflow_status(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(services.workflows.get(args.workflow_run_id))


def _workflow_resume(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(services.workflows.resume(args.workflow_run_id))


def _workflow_cancel(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(services.workflows.cancel(args.workflow_run_id))


def _workflow_events(args: argparse.Namespace) -> dict[str, object]:
    with _services(args) as services:
        return _dump(
            services.workflows.list_events(
                args.workflow_run_id, page=args.page, page_size=args.page_size
            )
        )


def _demo(args: argparse.Namespace) -> dict[str, object]:
    database = Path(args.database) if args.database else None
    return _dump(run_demo_m6(database, reset=args.reset))


def configure_m6_commands(commands: Any, plan_parser: argparse.ArgumentParser) -> None:
    """Add grouped commands while retaining the legacy flat command surface."""
    project = commands.add_parser("project", help="Create and inspect projects")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    create = project_sub.add_parser("create", help="Create a project")
    _common(create)
    create.add_argument("--title", required=True)
    create.add_argument("--genre", required=True)
    create.add_argument("--premise", required=True)
    create.add_argument("--chapters", type=int, required=True)
    create.add_argument("--words", type=int, default=300)
    create.add_argument("--language", default="zh-CN")
    create.add_argument("--tone")
    create.add_argument("--audience")
    create.add_argument("--additional-requirements", default="")
    create.set_defaults(handler=_project_create)
    listing = project_sub.add_parser("list", help="List projects")
    _common(listing)
    _page(listing)
    listing.add_argument("--search")
    listing.set_defaults(handler=_project_list)
    show = project_sub.add_parser("show", help="Show a project")
    _common(show)
    show.add_argument("--project-id", type=int, required=True)
    show.set_defaults(handler=_project_show)

    plan_sub = plan_parser.add_subparsers(dest="plan_command")
    generate = plan_sub.add_parser("generate", help="Generate a plan")
    _common(generate)
    generate.add_argument("--project-id", type=int, required=True)
    generate.add_argument("--replace-existing", action="store_true")
    generate.set_defaults(handler=_plan_generate)
    show_plan = plan_sub.add_parser("show", help="Show a plan")
    _common(show_plan)
    show_plan.add_argument("--project-id", type=int, required=True)
    show_plan.set_defaults(handler=_plan_show)

    chapter = commands.add_parser("chapter", help="Inspect and operate on chapters")
    chapter_sub = chapter.add_subparsers(dest="chapter_command", required=True)
    for name, handler in (("list", _chapter_list), ("versions", _chapter_versions)):
        item = chapter_sub.add_parser(name, help=f"{name.title()} chapters or versions")
        _common(item)
        _chapter_identity(item, number=name == "versions")
        _page(item)
        item.set_defaults(handler=handler)
    show_chapter = chapter_sub.add_parser("show", help="Show a chapter")
    _common(show_chapter)
    _chapter_identity(show_chapter, number=True)
    show_chapter.add_argument("--include-content", action="store_true")
    show_chapter.set_defaults(handler=_chapter_show)
    context = chapter_sub.add_parser("context", help="Show future-safe context metadata")
    _common(context)
    _chapter_identity(context, number=True)
    context.add_argument("--max-context-chars", type=int, default=24_000)
    context.set_defaults(handler=_chapter_context)
    generate_chapter = chapter_sub.add_parser("generate", help="Generate one chapter")
    _common(generate_chapter)
    _chapter_identity(generate_chapter, number=True)
    generate_chapter.add_argument("--regenerate", action="store_true")
    generate_chapter.add_argument("--max-context-chars", type=int, default=24_000)
    generate_chapter.set_defaults(handler=_chapter_generate)
    evaluate = chapter_sub.add_parser("evaluate", help="Evaluate one chapter")
    _common(evaluate)
    _chapter_identity(evaluate, number=True)
    evaluate.add_argument("--force", action="store_true")
    evaluate.add_argument(
        "--critic-scenario",
        choices=("normal", "death", "outline", "poor", "conflict"),
        default="normal",
    )
    evaluate.set_defaults(handler=_chapter_evaluate)
    diff = chapter_sub.add_parser("diff", help="Compare chapter versions")
    _common(diff)
    _chapter_identity(diff, number=True)
    diff.add_argument("--version-id", type=int, required=True)
    diff.add_argument("--old-version-id", type=int)
    diff.add_argument("--include-diff", action="store_true")
    diff.set_defaults(handler=_chapter_diff)

    evaluation = commands.add_parser("evaluation", help="Inspect evaluation history")
    evaluation_sub = evaluation.add_subparsers(dest="evaluation_command", required=True)
    evaluation_list = evaluation_sub.add_parser("list", help="List evaluations")
    _common(evaluation_list)
    _chapter_identity(evaluation_list, number=True)
    _page(evaluation_list)
    evaluation_list.set_defaults(handler=_evaluation_list)
    evaluation_show = evaluation_sub.add_parser("show", help="Show an evaluation")
    _common(evaluation_show)
    _chapter_identity(evaluation_show, number=True)
    evaluation_show.add_argument("--evaluation-id", type=int, required=True)
    evaluation_show.set_defaults(handler=_evaluation_show)

    conflict = commands.add_parser("conflict", help="Inspect and resolve conflicts")
    conflict_sub = conflict.add_subparsers(dest="conflict_command", required=True)
    conflict_list = conflict_sub.add_parser("list", help="List conflicts")
    _common(conflict_list)
    conflict_list.add_argument("--project-id", type=int, required=True)
    conflict_list.add_argument("--chapter-number", type=int)
    _page(conflict_list)
    conflict_list.set_defaults(handler=_conflict_list)
    resolve = conflict_sub.add_parser("resolve", help="Resolve a conflict")
    _common(resolve)
    resolve.add_argument("--project-id", type=int, required=True)
    resolve.add_argument("--conflict-id", type=int, required=True)
    resolve.add_argument("--note")
    resolve.set_defaults(handler=_conflict_resolve)

    fact = commands.add_parser("fact", help="Query accepted facts")
    fact_sub = fact.add_subparsers(dest="fact_command", required=True)
    fact_list = fact_sub.add_parser("list", help="List accepted facts")
    _common(fact_list)
    fact_list.add_argument("--project-id", type=int, required=True)
    fact_list.add_argument("--chapter-number", type=int)
    fact_list.add_argument("--valid-at-chapter", type=int)
    _page(fact_list)
    fact_list.set_defaults(handler=_fact_list)

    workflow = commands.add_parser("workflow", help="Run and inspect durable workflows")
    workflow_sub = workflow.add_subparsers(dest="workflow_command", required=True)
    run = workflow_sub.add_parser("run", help="Synchronously run a workflow")
    _common(run)
    _chapter_identity(run, number=True)
    run.add_argument("--max-revision-attempts", type=int, default=2)
    run.add_argument("--scenario", choices=("pass", "improve", "stagnate"), default="improve")
    run.add_argument("--pause-after-node")
    run.set_defaults(handler=_workflow_run)
    for name, handler in (
        ("status", _workflow_status),
        ("resume", _workflow_resume),
        ("cancel", _workflow_cancel),
        ("events", _workflow_events),
    ):
        item = workflow_sub.add_parser(name, help=f"{name.title()} a workflow")
        _common(item)
        item.add_argument("--workflow-run-id", type=int, required=True)
        if name in {"resume", "status"}:
            item.add_argument(
                "--scenario", choices=("pass", "improve", "stagnate"), default="improve"
            )
        if name == "events":
            _page(item)
        item.set_defaults(handler=handler)

    demo = commands.add_parser("demo", help="Run offline milestone demonstrations")
    demo_sub = demo.add_subparsers(dest="demo_command", required=True)
    demo_m6 = demo_sub.add_parser("m6", help="Run the complete offline M6 path")
    demo_m6.add_argument("--database")
    demo_m6.add_argument("--reset", action="store_true")
    demo_m6.add_argument("--output", choices=("human", "json"), default="human")
    demo_m6.set_defaults(handler=_demo)


def configure_demo_m6_alias(commands: Any) -> None:
    alias = commands.add_parser("demo-m6", help="Run the complete offline M6 path")
    alias.add_argument("--database")
    alias.add_argument("--reset", action="store_true")
    alias.add_argument("--output", choices=("human", "json"), default="human")
    alias.set_defaults(handler=_demo)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database", default="storyforge.db")
    parser.add_argument("--output", choices=("human", "json"), default="human")


def _page(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)


def _chapter_identity(parser: argparse.ArgumentParser, *, number: bool) -> None:
    parser.add_argument("--project-id", type=int, required=True)
    if number:
        parser.add_argument("--chapter-number", type=int, required=True)
