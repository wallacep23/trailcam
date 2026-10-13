"""Worker process: polls the job queue and runs handlers (DESIGN §6).

Run with ``trailcam-worker`` or ``python -m trailcam.pipeline.runner``. Stops gracefully on
SIGINT/SIGTERM after the current job finishes. Several workers may run against the same database.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import sys
import threading
import time
import traceback
import uuid
from types import FrameType
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from trailcam.config import Settings, get_settings
from trailcam.core.types import JobStatus
from trailcam.db.session import get_session_factory
from trailcam.log import bind_context, configure_logging
from trailcam.pipeline import jobs
from trailcam.pipeline.registry import HandlerSpec, JobContext, load_handlers

log = logging.getLogger("trailcam.worker")


class _Heartbeat:
    """Background thread that refreshes a running job's heartbeat."""

    def __init__(
        self, factory: sessionmaker[Session], job_id: uuid.UUID, interval_s: float
    ) -> None:
        self._factory = factory
        self._job_id = job_id
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"heartbeat-{job_id}", daemon=True)

    def __enter__(self) -> _Heartbeat:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval + 1)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                with self._factory() as session:
                    jobs.heartbeat(session, self._job_id)
            except Exception:
                log.warning("heartbeat failed", exc_info=True)


class Worker:
    """Claims and executes jobs. ``run_once`` is the unit the tests drive directly."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
        settings: Settings | None = None,
        handlers: dict[str, HandlerSpec] | None = None,
        worker_id: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.factory = session_factory or get_session_factory()
        self.handlers = handlers if handlers is not None else load_handlers()
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.stop_event = threading.Event()
        self._last_reap = 0.0

    @property
    def claimable_types(self) -> list[str]:
        wanted = self.settings.worker.job_types
        return [t for t in self.handlers if not wanted or t in wanted]

    def reap_if_due(self) -> int:
        now = time.monotonic()
        if now - self._last_reap < self.settings.worker.heartbeat_interval_s:
            return 0
        self._last_reap = now
        with self.factory() as session:
            n = jobs.reap_stale(session, self.settings.worker.stale_after_s)
        if n:
            log.warning("re-queued stale jobs", extra={"count": n})
        return n

    def run_once(self) -> JobStatus | None:
        """Claim and run at most one job. Returns its resulting status, or ``None`` if idle."""
        types = self.claimable_types
        if not types:
            return None
        with self.factory() as session:
            job = jobs.claim(session, self.worker_id, types)
            if job is None:
                return None
            ctx = JobContext(
                job_id=job.id,
                job_type=job.type,
                payload=dict(job.payload or {}),
                attempt=job.attempts,
                max_attempts=job.max_attempts,
                session_factory=self.factory,
            )
        return self._execute(ctx)

    def _execute(self, ctx: JobContext) -> JobStatus:
        spec = self.handlers[ctx.job_type]
        with bind_context(job_id=str(ctx.job_id), job_type=ctx.job_type, attempt=ctx.attempt):
            log.info("job started")
            started = time.monotonic()
            try:
                with _Heartbeat(
                    self.factory, ctx.job_id, self.settings.worker.heartbeat_interval_s
                ):
                    result = spec.func(ctx)
            except Exception as exc:
                fatal = isinstance(exc, jobs.FatalJobError)
                error = "".join(traceback.format_exception(exc))
                with self.factory() as session:
                    status = jobs.fail(
                        session, ctx.job_id, error, retryable=not fatal, defaults=self.settings.jobs
                    )
                level = logging.WARNING if status is JobStatus.QUEUED else logging.ERROR
                log.log(
                    level,
                    "job failed",
                    extra={"status": status.value, "error": f"{type(exc).__name__}: {exc}"},
                )
                return status
            with self.factory() as session:
                jobs.complete(session, ctx.job_id, _jsonable(result))
            log.info("job succeeded", extra={"duration_s": round(time.monotonic() - started, 3)})
            return JobStatus.SUCCEEDED

    def run_forever(self) -> None:
        log.info(
            "worker started", extra={"worker_id": self.worker_id, "types": self.claimable_types}
        )
        while not self.stop_event.is_set():
            try:
                self.reap_if_due()
                status = self.run_once()
            except Exception:
                log.exception("worker loop error; backing off")
                status = None
            if status is None:
                self.stop_event.wait(self.settings.worker.poll_interval_s)
        log.info("worker stopped", extra={"worker_id": self.worker_id})


def _jsonable(result: Any) -> dict[str, Any] | None:
    if result is None or isinstance(result, dict):
        return result
    return {"value": result}


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    worker = Worker(settings=settings)

    def _stop(signum: int, _frame: FrameType | None) -> None:
        log.info("shutdown requested", extra={"signal": signal.Signals(signum).name})
        worker.stop_event.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    worker.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
