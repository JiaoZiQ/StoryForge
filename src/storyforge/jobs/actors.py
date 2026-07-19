"""Dramatiq actors; each message contains only a durable Job ID."""

from __future__ import annotations

import dramatiq

from storyforge.application import DomainServiceFactory
from storyforge.database import create_database_engine, create_session_factory
from storyforge.jobs.broker import DramatiqJobBroker
from storyforge.jobs.handlers import JobHandlers
from storyforge.jobs.middleware import WorkerHeartbeatMiddleware, current_worker_id
from storyforge.jobs.worker import JobExecutor
from storyforge.services.jobs import JobService
from storyforge.settings import Settings

settings = Settings.from_env()
transport = DramatiqJobBroker(settings.redis_url, namespace=settings.queue_prefix)
redis_broker = transport.broker
redis_broker.add_middleware(WorkerHeartbeatMiddleware(settings))
dramatiq.set_broker(redis_broker)


def _execute(job_id: int) -> None:
    engine = create_database_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        factory = DomainServiceFactory(session_factory, settings)
        job_service = JobService(session_factory, settings)
        handlers = JobHandlers(session_factory, factory, settings, job_service)
        JobExecutor(session_factory, handlers, settings).execute(
            job_id, worker_id=current_worker_id()
        )
    finally:
        engine.dispose()


@dramatiq.actor(
    actor_name="storyforge_execute_default_job",
    queue_name=f"{settings.queue_prefix}.default",
    max_retries=0,
    time_limit=settings.job_default_timeout * 1000,
)
def execute_default_job(job_id: int) -> None:
    _execute(job_id)


@dramatiq.actor(
    actor_name="storyforge_execute_workflow_job",
    queue_name=f"{settings.queue_prefix}.workflow",
    max_retries=0,
    time_limit=settings.job_default_timeout * 1000,
)
def execute_workflow_job(job_id: int) -> None:
    _execute(job_id)


@dramatiq.actor(
    actor_name="storyforge_execute_indexing_job",
    queue_name=f"{settings.queue_prefix}.indexing",
    max_retries=0,
    time_limit=settings.job_default_timeout * 1000,
)
def execute_indexing_job(job_id: int) -> None:
    _execute(job_id)
