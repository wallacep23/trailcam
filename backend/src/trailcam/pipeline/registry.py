"""Job handler registry.

A handler is a plain function ``(ctx: JobContext) -> dict | None``. Pipeline stages register
themselves with :func:`job_handler`; the worker and the API both read :data:`HANDLERS` (the API to
validate ``POST /jobs``).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from trailcam.pipeline import jobs

log = logging.getLogger("trailcam.pipeline")


@dataclass(slots=True)
class JobContext:
    """What a handler gets: the job's identity and payload, a DB session factory, progress."""

    job_id: uuid.UUID
    job_type: str
    payload: dict[str, Any]
    attempt: int
    max_attempts: int
    session_factory: sessionmaker[Session]
    _last_progress: tuple[int, int | None] | None = field(default=None, repr=False)

    def progress(self, done: int, total: int | None = None, message: str | None = None) -> None:
        """Report progress (also refreshes the heartbeat)."""
        with self.session_factory() as session:
            jobs.report_progress(session, self.job_id, done, total, message)
        self._last_progress = (done, total)


Handler = Callable[[JobContext], "dict[str, Any] | None"]


@dataclass(frozen=True, slots=True)
class HandlerSpec:
    job_type: str
    func: Handler
    description: str
    user_runnable: bool


HANDLERS: dict[str, HandlerSpec] = {}


def job_handler(
    job_type: str, *, description: str = "", user_runnable: bool = False
) -> Callable[[Handler], Handler]:
    """Register ``func`` as the handler for ``job_type``.

    ``user_runnable`` handlers may be enqueued directly through ``POST /api/v1/jobs``.
    """

    def decorator(func: Handler) -> Handler:
        if job_type in HANDLERS and HANDLERS[job_type].func is not func:
            raise ValueError(f"duplicate handler for job type {job_type!r}")
        HANDLERS[job_type] = HandlerSpec(
            job_type, func, description or (func.__doc__ or "").strip(), user_runnable
        )
        return func

    return decorator


def load_handlers() -> dict[str, HandlerSpec]:
    """Import every stage module so its handlers register, then return the registry."""
    from trailcam.pipeline import stages  # noqa: F401, PLC0415 - import for side effects

    return HANDLERS
