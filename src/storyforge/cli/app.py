"""Offline-first command line interface for milestone three."""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from alembic import command
from alembic.config import Config

from storyforge.agents import FactExtractorAgent, PlannerAgent, WriterAgent
from storyforge.database import create_database_engine, create_session_factory
from storyforge.demo import build_demo_provider
from storyforge.exceptions import StoryForgeError
from storyforge.prompts import build_prompt_registry
from storyforge.repositories import ChapterRepository, ProjectRepository
from storyforge.schemas.context import ContextBuildRequest
from storyforge.schemas.domain import ProjectCreate
from storyforge.schemas.generation import ChapterGenerationRequest
from storyforge.services import (
    ChapterGenerationService,
    ContextBuilder,
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

    demo = commands.add_parser("demo-m3", help="Run the complete offline M3 path")
    demo.add_argument("--database", default="storyforge-m3-demo.sqlite3")
    demo.add_argument("--reset", action="store_true")
    demo.set_defaults(handler=_demo)
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
