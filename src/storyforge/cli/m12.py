"""Milestone 12 whole-book CLI commands with JSON-safe output."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, cast

from pydantic import BaseModel
from sqlalchemy import Engine

from storyforge.application import BookQueryApplicationService, JobApplicationService
from storyforge.database import SessionFactory, create_database_engine, create_session_factory
from storyforge.enums import BookRunMode, JobStatus
from storyforge.m12_demo import run_demo_m12
from storyforge.schemas.books import BookRunCreateRequest, BookRunResumeRequest
from storyforge.services import BookRunService
from storyforge.settings import Settings


def _dump(model: BaseModel) -> dict[str, object]:
    return cast(dict[str, object], model.model_dump(mode="json"))


@contextmanager
def _services() -> Iterator[
    tuple[
        Engine,
        SessionFactory,
        Settings,
        BookRunService,
        BookQueryApplicationService,
        JobApplicationService,
    ]
]:
    settings = Settings.from_env()
    engine = create_database_engine(settings.database_url)
    sessions = create_session_factory(engine)
    try:
        yield (
            engine,
            sessions,
            settings,
            BookRunService(sessions, settings),
            BookQueryApplicationService(sessions),
            JobApplicationService(sessions, settings),
        )
    finally:
        engine.dispose()


def _run(args: argparse.Namespace) -> dict[str, object]:
    with _services() as (_, sessions, settings, runs, _, jobs):
        accepted = runs.create(
            args.project_id,
            BookRunCreateRequest(
                mode=BookRunMode(args.mode),
                max_chapter_retries=args.max_chapter_retries,
                max_global_revision_rounds=args.max_global_revision_rounds,
                max_estimated_cost=args.max_cost,
                max_total_tokens=args.max_tokens,
                max_provider_calls=args.max_provider_calls,
            ),
            external_idempotency_key=args.idempotency_key,
        )
        if not args.wait:
            return _dump(accepted)
        _execute_inline_if_needed(sessions, settings, accepted.job_id)
        job = _wait(jobs, accepted.job_id, interval=args.poll_interval)
        args.result_exit_code = 0 if job.status is JobStatus.SUCCEEDED else 9
        return _dump(runs.get(accepted.book_run_id))


def _list(args: argparse.Namespace) -> dict[str, object]:
    with _services() as (_, _, _, runs, _, _):
        return _dump(runs.list_project(args.project_id, page=args.page, page_size=args.page_size))


def _status(args: argparse.Namespace) -> dict[str, object]:
    with _services() as (_, _, _, runs, _, _):
        return _dump(runs.get(args.book_run_id))


def _watch(args: argparse.Namespace) -> dict[str, object]:
    with _services() as (_, _, _, runs, _, jobs):
        run = runs.get(args.book_run_id)
        if run.job_id is None:
            raise ValueError("BookRun has no top-level Job")
        if _watch_sse(args):
            refreshed = runs.get(args.book_run_id)
            if refreshed.status.value in {
                "completed",
                "completed_needs_review",
                "cancelled",
                "failed",
            }:
                args.result_exit_code = (
                    0 if refreshed.status.value in {"completed", "completed_needs_review"} else 9
                )
                return _dump(refreshed)
        last: tuple[str, int, str] | None = None
        while True:
            job = jobs.get(run.job_id)
            marker = (job.status.value, job.progress, job.current_step or "waiting")
            if args.output == "human" and marker != last:
                print(f"{marker[0]}: {marker[1]}% ({marker[2]})")
                last = marker
            if job.status in {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
                JobStatus.DEAD_LETTERED,
            }:
                args.result_exit_code = 0 if job.status is JobStatus.SUCCEEDED else 9
                return _dump(runs.get(args.book_run_id))
            time.sleep(args.poll_interval)


def _watch_sse(args: argparse.Namespace) -> bool:
    """Follow the safe API event stream; return false to activate DB polling fallback."""
    base_url = str(args.api_url).rstrip("/")
    url = f"{base_url}/api/v1/book-runs/{args.book_run_id}/events/stream"
    request = urllib.request.Request(
        url,
        headers={"Accept": "text/event-stream"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=args.sse_timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="strict").strip()
                if not line.startswith("data:"):
                    continue
                payload = json.loads(line[5:].strip())
                if not isinstance(payload, dict):
                    continue
                if args.output == "human":
                    status = payload.get("status", "running")
                    progress = payload.get("progress", "?")
                    step = payload.get("step", "waiting")
                    print(f"{status}: {progress}% ({step})")
                if payload.get("status") in {
                    "succeeded",
                    "failed",
                    "cancelled",
                    "dead_lettered",
                }:
                    return True
    except (
        OSError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ):
        return False
    return False


def _control(args: argparse.Namespace) -> dict[str, object]:
    with _services() as (_, _, _, runs, _, _):
        actions: dict[str, Callable[[], BaseModel]] = {
            "pause": lambda: runs.request_pause(args.book_run_id),
            "resume": lambda: runs.resume(
                args.book_run_id,
                BookRunResumeRequest(
                    max_estimated_cost=args.max_cost,
                    max_total_tokens=args.max_tokens,
                    max_provider_calls=args.max_provider_calls,
                ),
            ),
            "cancel": lambda: runs.request_cancel(args.book_run_id),
        }
        return _dump(actions[args.book_command]())


def _snapshots(args: argparse.Namespace) -> dict[str, object]:
    with _services() as (_, _, _, _, queries, _):
        return _dump(queries.snapshots(args.project_id))


def _snapshot_query(args: argparse.Namespace) -> dict[str, object]:
    with _services() as (_, _, _, _, queries, _):
        actions: dict[str, Callable[[], BaseModel]] = {
            "evaluation": lambda: queries.evaluation(args.snapshot_id),
            "timeline": lambda: queries.timeline(
                args.snapshot_id, page=args.page, page_size=args.page_size
            ),
            "characters": lambda: queries.character_arcs(args.snapshot_id),
            "relationships": lambda: queries.relationships(args.snapshot_id),
            "foreshadowing": lambda: queries.foreshadowing(args.snapshot_id),
            "pacing": lambda: queries.pacing(args.snapshot_id),
            "transitions": lambda: queries.transitions(args.snapshot_id),
            "revision-plan": lambda: queries.revision_plan(args.snapshot_id),
        }
        return _dump(actions[args.book_command]())


def _demo(_args: argparse.Namespace) -> dict[str, object]:
    with _services() as (_engine, sessions, settings, _runs, _queries, _jobs):
        return run_demo_m12(sessions, settings)


def _execute_inline_if_needed(sessions: SessionFactory, settings: Settings, job_id: int) -> None:
    if settings.job_execution_mode != "inline":
        return
    from storyforge.application.factory import DomainServiceFactory
    from storyforge.jobs.handlers import JobHandlers
    from storyforge.jobs.worker import JobExecutor
    from storyforge.services.jobs import JobService

    factory = DomainServiceFactory(sessions, settings)
    handlers = JobHandlers(sessions, factory, settings, JobService(sessions, settings))
    JobExecutor(sessions, handlers, settings, heartbeat_thread=False).execute(
        job_id, worker_id="storyforge-cli-inline"
    )


def _wait(service: JobApplicationService, job_id: int, *, interval: float):  # type: ignore[no-untyped-def]
    while True:
        job = service.get(job_id)
        if job.status in {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.DEAD_LETTERED,
        }:
            return job
        time.sleep(interval)


def _output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", choices=("human", "json"), default="json")


def configure_m12_commands(commands: Any) -> None:
    book = commands.add_parser("book", help="Run and inspect whole-book workflows")
    sub = book.add_subparsers(dest="book_command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--project-id", type=int, required=True)
    run.add_argument("--mode", choices=tuple(BookRunMode), default="sequential")
    run.add_argument("--max-chapter-retries", type=int)
    run.add_argument("--max-global-revision-rounds", type=int)
    run.add_argument("--max-cost", type=str)
    run.add_argument("--max-tokens", type=int)
    run.add_argument("--max-provider-calls", type=int)
    run.add_argument("--idempotency-key")
    run.add_argument("--wait", action="store_true")
    run.add_argument("--poll-interval", type=float, default=0.25)
    _output(run)
    run.set_defaults(handler=_run)
    listing = sub.add_parser("list")
    listing.add_argument("--project-id", type=int, required=True)
    listing.add_argument("--page", type=int, default=1)
    listing.add_argument("--page-size", type=int, default=20)
    _output(listing)
    listing.set_defaults(handler=_list)
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--book-run-id", type=int, required=True)
    _output(status_parser)
    status_parser.set_defaults(handler=_status)
    watch = sub.add_parser("watch")
    watch.add_argument("--book-run-id", type=int, required=True)
    watch.add_argument(
        "--api-url",
        default=os.getenv("STORYFORGE_API_URL", "http://127.0.0.1:8000"),
    )
    watch.add_argument("--sse-timeout", type=float, default=2.0)
    watch.add_argument("--poll-interval", type=float, default=0.5)
    _output(watch)
    watch.set_defaults(handler=_watch)
    for name in ("pause", "resume", "cancel"):
        control = sub.add_parser(name)
        control.add_argument("--book-run-id", type=int, required=True)
        control.add_argument("--max-cost", type=str)
        control.add_argument("--max-tokens", type=int)
        control.add_argument("--max-provider-calls", type=int)
        _output(control)
        control.set_defaults(handler=_control)
    snapshots = sub.add_parser("snapshots")
    snapshots.add_argument("--project-id", type=int, required=True)
    _output(snapshots)
    snapshots.set_defaults(handler=_snapshots)
    for name in (
        "evaluation",
        "timeline",
        "characters",
        "relationships",
        "foreshadowing",
        "pacing",
        "transitions",
        "revision-plan",
    ):
        query = sub.add_parser(name)
        query.add_argument("--snapshot-id", type=int, required=True)
        query.add_argument("--page", type=int, default=1)
        query.add_argument("--page-size", type=int, default=100)
        _output(query)
        query.set_defaults(handler=_snapshot_query)
    demo = commands.add_parser("demo-m12", help="Run the offline five-chapter M12 demo")
    _output(demo)
    demo.set_defaults(handler=_demo)
