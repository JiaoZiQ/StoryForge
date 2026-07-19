"""Milestone 11 asynchronous job commands."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, cast

from pydantic import BaseModel
from sqlalchemy import Engine

from storyforge.application import JobApplicationService
from storyforge.database import SessionFactory, create_database_engine, create_session_factory
from storyforge.enums import JobStatus, JobType
from storyforge.m11_demo import run_demo_m11
from storyforge.schemas.jobs import JobCreateRequest, JobResponse
from storyforge.settings import Settings


def _dump(model: BaseModel) -> dict[str, object]:
    return cast(dict[str, object], model.model_dump(mode="json"))


@contextmanager
def _service():  # type: ignore[no-untyped-def]
    settings = Settings.from_env()
    engine: Engine = create_database_engine(settings.database_url)
    sessions: SessionFactory = create_session_factory(engine)
    try:
        yield engine, sessions, settings, JobApplicationService(sessions, settings)
    finally:
        engine.dispose()


def _submit(args: argparse.Namespace) -> dict[str, object]:
    with _service() as (_, _, _, service):
        raw_payload = json.loads(args.payload_json)
        if not isinstance(raw_payload, dict):
            raise ValueError("--payload-json must contain a JSON object")
        accepted = service.create(
            JobCreateRequest(
                job_type=JobType(args.type),
                project_id=args.project_id,
                chapter_number=args.chapter_number,
                workflow_run_id=args.workflow_run_id,
                operation=args.operation,
                payload=raw_payload,
                idempotency_key=args.idempotency_key,
                priority=args.priority,
            )
        )
        if not args.wait:
            return _dump(accepted)
        result = _wait_for_terminal(
            service,
            accepted.job_id,
            interval=args.poll_interval,
            cancel_on_interrupt=args.cancel_on_interrupt,
        )
        args.result_exit_code = _terminal_exit_code(result.status)
        return _dump(result)


def _show(args: argparse.Namespace) -> dict[str, object]:
    with _service() as (_, _, _, service):
        return _dump(service.get(args.job_id))


def _list(args: argparse.Namespace) -> dict[str, object]:
    with _service() as (_, _, _, service):
        return _dump(
            service.list_jobs(
                page=args.page,
                page_size=args.page_size,
                status=JobStatus(args.status) if args.status else None,
                job_type=JobType(args.type) if args.type else None,
                project_id=args.project_id,
                chapter_number=args.chapter_number,
            )
        )


def _events(args: argparse.Namespace) -> dict[str, object]:
    with _service() as (_, _, _, service):
        return _dump(service.events(args.job_id, page=1, page_size=500))


def _watch(args: argparse.Namespace) -> dict[str, object]:
    with _service() as (_, _, _, service):
        last: list[tuple[JobStatus, int, str | None]] = []

        def show_progress(job: JobResponse) -> None:
            marker = (job.status, job.progress, job.current_step)
            if marker == (last[-1] if last else None):
                return
            last.append(marker)
            print(f"{job.status.value}: {job.progress}% ({job.current_step or 'waiting'})")

        result = _wait_for_terminal(
            service,
            args.job_id,
            interval=args.poll_interval,
            cancel_on_interrupt=args.cancel_on_interrupt,
            on_update=show_progress if args.output == "human" else None,
        )
        args.result_exit_code = _terminal_exit_code(result.status)
        return _dump(result)


def _control(args: argparse.Namespace) -> dict[str, object]:
    with _service() as (_, _, _, service):
        actions: dict[str, Callable[[int], JobResponse]] = {
            "cancel": service.cancel,
            "pause": service.pause,
            "resume": service.resume,
            "retry": service.retry,
            "discard": service.discard,
        }
        return _dump(actions[args.job_command](args.job_id))


def _workers(_: argparse.Namespace) -> dict[str, object]:
    with _service() as (_, _, settings, service):
        reachable = settings.job_execution_mode == "inline"
        if not reachable:
            from storyforge.jobs.broker import DramatiqJobBroker

            reachable = DramatiqJobBroker(
                settings.redis_url, namespace=settings.queue_prefix
            ).ping()
        return _dump(service.health(reachable))


def _demo(_: argparse.Namespace) -> dict[str, object]:
    with _service() as (_, sessions, settings, _):
        return run_demo_m11(sessions, settings)


def submit_job_request(
    request: JobCreateRequest,
    *,
    wait: bool,
    poll_interval: float,
    cancel_on_interrupt: bool,
) -> tuple[dict[str, object], int]:
    """Shared adapter for grouped CLI commands opting into queue execution."""
    with _service() as (_, _, _, service):
        accepted = service.create(request)
        if not wait:
            return _dump(accepted), 0
        result = _wait_for_terminal(
            service,
            accepted.job_id,
            interval=poll_interval,
            cancel_on_interrupt=cancel_on_interrupt,
        )
        return _dump(result), _terminal_exit_code(result.status)


def _wait_for_terminal(
    service: JobApplicationService,
    job_id: int,
    *,
    interval: float,
    cancel_on_interrupt: bool,
    on_update: Callable[[JobResponse], None] | None = None,
) -> JobResponse:
    try:
        while True:
            job = service.get(job_id)
            if on_update is not None:
                on_update(job)
            if job.status in {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
                JobStatus.DEAD_LETTERED,
            }:
                return job
            time.sleep(interval)
    except KeyboardInterrupt:
        if cancel_on_interrupt:
            service.cancel(job_id)
        raise


def _terminal_exit_code(status: JobStatus) -> int:
    return {
        JobStatus.SUCCEEDED: 0,
        JobStatus.CANCELLED: 7,
        JobStatus.DEAD_LETTERED: 8,
        JobStatus.FAILED: 9,
    }.get(status, 0)


def _output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", choices=("human", "json"), default="json")


def configure_m11_commands(commands: Any) -> None:
    job = commands.add_parser("job", help="Submit and inspect asynchronous jobs")
    sub = job.add_subparsers(dest="job_command", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("--type", choices=tuple(JobType), required=True)
    submit.add_argument("--project-id", type=int)
    submit.add_argument("--chapter-number", type=int)
    submit.add_argument("--workflow-run-id", type=int)
    submit.add_argument("--operation", default="run")
    submit.add_argument("--idempotency-key")
    submit.add_argument("--priority", type=int, default=5)
    submit.add_argument("--payload-json", default="{}")
    submit.add_argument("--wait", action="store_true")
    submit.add_argument("--poll-interval", type=float, default=0.25)
    submit.add_argument("--cancel-on-interrupt", action="store_true")
    _output(submit)
    submit.set_defaults(handler=_submit)
    listing = sub.add_parser("list")
    listing.add_argument("--page", type=int, default=1)
    listing.add_argument("--page-size", type=int, default=20)
    listing.add_argument("--status", choices=tuple(JobStatus))
    listing.add_argument("--type", choices=tuple(JobType))
    listing.add_argument("--project-id", type=int)
    listing.add_argument("--chapter-number", type=int)
    _output(listing)
    listing.set_defaults(handler=_list)
    show = sub.add_parser("show")
    show.add_argument("--job-id", type=int, required=True)
    _output(show)
    show.set_defaults(handler=_show)
    events = sub.add_parser("events")
    events.add_argument("--job-id", type=int, required=True)
    _output(events)
    events.set_defaults(handler=_events)
    watch = sub.add_parser("watch")
    watch.add_argument("--job-id", type=int, required=True)
    watch.add_argument("--poll-interval", type=float, default=0.25)
    watch.add_argument("--cancel-on-interrupt", action="store_true")
    _output(watch)
    watch.set_defaults(handler=_watch)
    dead_letter = sub.add_parser("dead-letter")
    dead_letter.add_argument("--page", type=int, default=1)
    dead_letter.add_argument("--page-size", type=int, default=20)
    dead_letter.add_argument("--status", default=JobStatus.DEAD_LETTERED.value)
    dead_letter.add_argument("--type", choices=tuple(JobType))
    dead_letter.add_argument("--project-id", type=int)
    dead_letter.add_argument("--chapter-number", type=int)
    _output(dead_letter)
    dead_letter.set_defaults(handler=_list)
    for name in ("cancel", "pause", "resume", "retry", "discard"):
        control = sub.add_parser(name)
        control.add_argument("--job-id", type=int, required=True)
        _output(control)
        control.set_defaults(handler=_control)
    workers = commands.add_parser("worker-status", help="Show safe worker heartbeats")
    _output(workers)
    workers.set_defaults(handler=_workers)
    worker = commands.add_parser("worker", help="Inspect safe worker health")
    worker_sub = worker.add_subparsers(dest="worker_command", required=True)
    worker_status = worker_sub.add_parser("status")
    _output(worker_status)
    worker_status.set_defaults(handler=_workers)
    demo = commands.add_parser("demo-m11", help="Run the distributed M11 demonstration")
    _output(demo)
    demo.set_defaults(handler=_demo)
