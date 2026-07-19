"""Dramatiq worker-process registration and idle heartbeat middleware."""

from __future__ import annotations

import atexit
import logging
import os
import threading

from dramatiq import Middleware
from dramatiq.broker import Broker
from sqlalchemy.exc import SQLAlchemyError

from storyforge import __version__
from storyforge.database import create_database_engine, create_session_factory
from storyforge.models.base import utc_now
from storyforge.repositories import WorkerRepository
from storyforge.settings import Settings

logger = logging.getLogger(__name__)


def current_worker_id() -> str:
    """Return one stable, content-free identifier per worker subprocess."""
    worker_name = os.getenv("STORYFORGE_WORKER_ID") or os.getenv("HOSTNAME") or "worker"
    return f"{worker_name}-{os.getpid()}"


class WorkerHeartbeat:
    """Keep an idle or busy worker discoverable without touching its Job ownership."""

    def __init__(self, settings: Settings, worker_id: str) -> None:
        self._settings = settings
        self._worker_id = worker_id
        self._engine = create_database_engine(settings.database_url)
        self._sessions = create_session_factory(self._engine)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def beat(self) -> None:
        """Write one atomic keepalive; callers deliberately tolerate database outages."""
        with self._sessions.begin() as session:
            WorkerRepository(session).keepalive(
                worker_id=self._worker_id,
                queue_name="all",
                version=__version__,
                now=utc_now(),
            )

    def start(self) -> None:
        if self._thread is not None:
            return
        try:
            self.beat()
        except SQLAlchemyError:
            logger.warning("worker_initial_heartbeat_failed")
        self._thread = threading.Thread(
            target=self._run,
            name="storyforge-worker-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._settings.worker_heartbeat_seconds * 2))
        self._engine.dispose()

    def _run(self) -> None:
        while not self._stop.wait(self._settings.worker_heartbeat_seconds):
            try:
                self.beat()
            except SQLAlchemyError:
                continue


class WorkerHeartbeatMiddleware(Middleware):
    """Start one heartbeat loop inside every Dramatiq worker subprocess."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._heartbeat: WorkerHeartbeat | None = None

    def after_process_boot(self, broker: Broker) -> None:
        del broker
        heartbeat = WorkerHeartbeat(self._settings, current_worker_id())
        heartbeat.start()
        atexit.register(heartbeat.stop)
        self._heartbeat = heartbeat
