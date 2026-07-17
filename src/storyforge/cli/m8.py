"""Milestone 8 memory, graph, retrieval, and PostgreSQL demo commands."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine

from storyforge.application import DomainServiceFactory, MemoryApplicationService
from storyforge.database import SessionFactory, create_database_engine, create_session_factory
from storyforge.enums import GraphEntityType, GraphPredicate
from storyforge.m8_demo import run_demo_m8
from storyforge.schemas.api import MemoryReindexRequest, RetrievalSearchRequest
from storyforge.settings import Settings


@dataclass(frozen=True, slots=True)
class _MemoryServices:
    engine: Engine
    memory: MemoryApplicationService


@contextmanager
def _services() -> Iterator[_MemoryServices]:
    settings = Settings.from_env()
    engine = create_database_engine(settings.database_url)
    session_factory: SessionFactory = create_session_factory(engine)
    factory = DomainServiceFactory(session_factory, settings)
    try:
        yield _MemoryServices(
            engine=engine,
            memory=MemoryApplicationService(session_factory, factory, settings),
        )
    finally:
        engine.dispose()


def _dump(value: BaseModel) -> dict[str, object]:
    return value.model_dump(mode="json")


def _memory_status(args: argparse.Namespace) -> dict[str, object]:
    with _services() as services:
        return _dump(
            services.memory.list_status(args.project_id, page=args.page, page_size=args.page_size)
        )


def _memory_list(args: argparse.Namespace) -> dict[str, object]:
    with _services() as services:
        page = services.memory.list_memory(
            args.project_id,
            page=args.page,
            page_size=args.page_size,
            source_type=args.source_type,
            chapter_number=args.chapter_number,
        )
        payload = _dump(page)
        if args.include_content:
            payload["items"] = [
                _dump(services.memory.get_memory(args.project_id, item.id, include_content=True))
                for item in page.items
            ]
        return payload


def _memory_show(args: argparse.Namespace) -> dict[str, object]:
    with _services() as services:
        return _dump(
            services.memory.get_memory(
                args.project_id,
                args.memory_id,
                include_content=args.include_content,
            )
        )


def _memory_reindex(args: argparse.Namespace) -> dict[str, object]:
    with _services() as services:
        return _dump(
            services.memory.reindex(
                args.project_id,
                MemoryReindexRequest(
                    chapter_version_id=args.chapter_version_id,
                    all_accepted_chapters=args.all_accepted_chapters,
                    force=args.force,
                ),
            )
        )


def _retrieval_search(args: argparse.Namespace) -> dict[str, object]:
    with _services() as services:
        return _dump(
            services.memory.search(
                args.project_id,
                RetrievalSearchRequest(
                    query=args.query,
                    current_chapter=args.current_chapter,
                    character_names=args.character,
                    location_names=args.location,
                    source_types=args.source_type,
                    top_k=args.top_k,
                    max_context_chars=args.max_context_chars,
                    include_sources=args.include_source or None,
                    debug=args.debug,
                ),
            )
        )


def _graph_entities(args: argparse.Namespace) -> dict[str, object]:
    with _services() as services:
        return _dump(
            services.memory.list_entities(
                args.project_id,
                page=args.page,
                page_size=args.page_size,
                entity_type=(GraphEntityType(args.entity_type) if args.entity_type else None),
                search=args.search,
            )
        )


def _graph_relations(args: argparse.Namespace) -> dict[str, object]:
    with _services() as services:
        return _dump(
            services.memory.list_relations(
                args.project_id,
                current_chapter=args.current_chapter,
                page=args.page,
                page_size=args.page_size,
                predicate=GraphPredicate(args.predicate) if args.predicate else None,
            )
        )


def _graph_neighbors(args: argparse.Namespace) -> dict[str, object]:
    with _services() as services:
        return _dump(
            services.memory.neighbors(
                args.project_id,
                args.entity_id,
                current_chapter=args.current_chapter,
                max_hops=args.max_hops,
            )
        )


def _demo_m8(_: argparse.Namespace) -> dict[str, object]:
    return _dump(run_demo_m8())


def configure_m8_commands(commands: Any) -> None:
    """Register M8 commands using application services rather than ORM access."""
    memory = commands.add_parser("memory", help="Inspect and reindex accepted memory")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    status = memory_sub.add_parser("status", help="Show memory indexing attempts")
    _common(status)
    _project(status)
    _page(status)
    status.set_defaults(handler=_memory_status)
    listing = memory_sub.add_parser("list", help="List accepted memory chunks")
    _common(listing)
    _project(listing)
    _page(listing)
    listing.add_argument("--source-type")
    listing.add_argument("--chapter-number", type=int)
    listing.add_argument("--include-content", action="store_true")
    listing.set_defaults(handler=_memory_list)
    show = memory_sub.add_parser("show", help="Show one accepted memory chunk")
    _common(show)
    _project(show)
    show.add_argument("--memory-id", type=int, required=True)
    show.add_argument("--include-content", action="store_true")
    show.set_defaults(handler=_memory_show)
    reindex = memory_sub.add_parser("reindex", help="Synchronously reindex accepted memory")
    _common(reindex)
    _project(reindex)
    scope = reindex.add_mutually_exclusive_group(required=True)
    scope.add_argument("--chapter-version-id", type=int)
    scope.add_argument("--all-accepted-chapters", action="store_true")
    reindex.add_argument("--force", action="store_true")
    reindex.set_defaults(handler=_memory_reindex)

    retrieval = commands.add_parser("retrieval", help="Run explainable hybrid retrieval")
    retrieval_sub = retrieval.add_subparsers(dest="retrieval_command", required=True)
    search = retrieval_sub.add_parser("search", help="Search past-only accepted memory")
    _common(search)
    _project(search)
    search.add_argument("--query", required=True)
    search.add_argument("--current-chapter", type=int, required=True)
    search.add_argument("--character", action="append", default=[])
    search.add_argument("--location", action="append", default=[])
    search.add_argument("--source-type", action="append", default=[])
    search.add_argument(
        "--include-source",
        action="append",
        choices=("keyword", "vector", "fact", "graph"),
        default=[],
    )
    search.add_argument("--top-k", type=int, default=20)
    search.add_argument("--max-context-chars", type=int, default=16_000)
    search.add_argument("--debug", action="store_true")
    search.set_defaults(handler=_retrieval_search)

    graph = commands.add_parser("graph", help="Inspect the accepted relational story graph")
    graph_sub = graph.add_subparsers(dest="graph_command", required=True)
    entities = graph_sub.add_parser("entities", help="List accepted graph entities")
    _common(entities)
    _project(entities)
    _page(entities)
    entities.add_argument("--entity-type", choices=tuple(GraphEntityType))
    entities.add_argument("--search")
    entities.set_defaults(handler=_graph_entities)
    relations = graph_sub.add_parser("relations", help="List accepted past relations")
    _common(relations)
    _project(relations)
    _page(relations)
    relations.add_argument("--current-chapter", type=int, required=True)
    relations.add_argument("--predicate", choices=tuple(GraphPredicate))
    relations.set_defaults(handler=_graph_relations)
    neighbors = graph_sub.add_parser("neighbors", help="Expand one entity by one or two hops")
    _common(neighbors)
    _project(neighbors)
    neighbors.add_argument("--entity-id", type=int, required=True)
    neighbors.add_argument("--current-chapter", type=int, required=True)
    neighbors.add_argument("--max-hops", type=int, choices=(1, 2), default=1)
    neighbors.set_defaults(handler=_graph_neighbors)

    demo = commands.add_parser("demo-m8", help="Run PostgreSQL pgvector M8 demonstration")
    demo.add_argument("--output", choices=("human", "json"), default="human")
    demo.set_defaults(handler=_demo_m8)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", choices=("human", "json"), default="human")


def _project(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", type=int, required=True)


def _page(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)
