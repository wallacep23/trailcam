"""Postgres-backed job queue (DESIGN §6, ADR 0003).

A job is a row in ``job``. Workers claim with ``SELECT … FOR UPDATE SKIP LOCKED`` so any number of
workers can poll the same table without double-processing. Every state change is a short
transaction, so jobs are transactional with the data they produce.

Lifecycle::

    queued ──claim──▶ running ──complete──▶ succeeded
       ▲                 │
       └── retry (backoff, attempts < max) ◀── fail ──▶ failed (attempts exhausted / fatal)

* **Idempotency** (CLAUDE.md conventions): pass ``dedupe_key`` — typically
  :func:`stage_key` ``(target, stage, model_version, config_hash)``. While a job with that key is
  queued or running, enqueueing again returns the existing job; once it has succeeded, enqueueing
  again returns the succeeded job unless ``force=True``.
* **Progress**: :func:`report_progress` stores ``{done, total, fraction, message}`` and refreshes
  the heartbeat.
* **Crash safety**: :func:`reap_stale` re-queues running jobs whose heartbeat is older than the
  configured timeout (the worker died), counting that as a failed attempt.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from trailcam.config import JobDefaults, get_settings
from trailcam.core.backoff import progress_fraction, retry_delay_s
from trailcam.core.ids import uuid7
from trailcam.core.types import JobStatus
from trailcam.db.models import Job

MAX_ERROR_CHARS = 8000


class JobError(Exception):
    """Base class for queue errors."""


class FatalJobError(JobError):
    """Raise from a handler to fail the job immediately, without retrying."""


class InvalidTransitionError(JobError):
    """The job is not in a state that allows the requested change."""


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    job: Job
    created: bool


def config_hash(config: dict[str, Any]) -> str:
    """Stable short hash of a stage configuration (NFR-5)."""
    blob = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def stage_key(target: uuid.UUID | str, stage: str, model_version: str, cfg_hash: str) -> str:
    """Idempotency key ``target:stage:model_version:config_hash`` for a pipeline stage job."""
    return f"{target}:{stage}:{model_version}:{cfg_hash}"


def _now() -> datetime:
    return datetime.now(UTC)


def enqueue(
    session: Session,
    job_type: str,
    payload: dict[str, Any] | None = None,
    *,
    dedupe_key: str | None = None,
    priority: int = 0,
    max_attempts: int | None = None,
    run_after: datetime | None = None,
    force: bool = False,
) -> EnqueueResult:
    """Add a job (flushes, does not commit). Returns the existing job if ``dedupe_key`` matches."""
    defaults = get_settings().jobs
    if dedupe_key is not None:
        existing = _find_by_key(session, dedupe_key, include_succeeded=not force)
        if existing is not None:
            return EnqueueResult(existing, created=False)

    job = Job(
        id=uuid7(),
        type=job_type,
        payload=payload or {},
        status=JobStatus.QUEUED.value,
        priority=priority,
        attempts=0,
        max_attempts=max_attempts or defaults.max_attempts,
        dedupe_key=dedupe_key,
        run_after=run_after or _now(),
    )
    try:
        with session.begin_nested():  # savepoint: a concurrent enqueue may win the unique index
            session.add(job)
            session.flush()
    except IntegrityError:
        if dedupe_key is None:
            raise
        existing = _find_by_key(session, dedupe_key, include_succeeded=False)
        if existing is None:
            raise
        return EnqueueResult(existing, created=False)
    return EnqueueResult(job, created=True)


def _find_by_key(session: Session, dedupe_key: str, *, include_succeeded: bool) -> Job | None:
    statuses = [JobStatus.QUEUED.value, JobStatus.RUNNING.value]
    if include_succeeded:
        statuses.append(JobStatus.SUCCEEDED.value)
    return session.scalars(
        select(Job)
        .where(Job.dedupe_key == dedupe_key, Job.status.in_(statuses))
        .order_by(Job.created_at.desc())
        .limit(1)
    ).first()


_CLAIM_SQL = text(
    """
    UPDATE job
       SET status = 'running',
           attempts = attempts + 1,
           locked_by = :worker_id,
           started_at = now(),
           heartbeat_at = now(),
           finished_at = NULL,
           updated_at = now()
     WHERE id = (
            SELECT id FROM job
             WHERE status = 'queued'
               AND run_after <= now()
               AND (CAST(:types AS text[]) IS NULL OR type = ANY(CAST(:types AS text[])))
             ORDER BY priority DESC, run_after, id
             LIMIT 1
             FOR UPDATE SKIP LOCKED
           )
    RETURNING id
    """
)


def claim(session: Session, worker_id: str, job_types: list[str] | None = None) -> Job | None:
    """Atomically claim the next runnable job, or return ``None``. Commits."""
    job_id = session.execute(
        _CLAIM_SQL, {"worker_id": worker_id, "types": job_types or None}
    ).scalar_one_or_none()
    session.commit()
    if job_id is None:
        return None
    return session.get(Job, job_id, populate_existing=True)


def report_progress(
    session: Session,
    job_id: uuid.UUID,
    done: int,
    total: int | None = None,
    message: str | None = None,
) -> None:
    """Record progress and heartbeat for a running job. Commits."""
    progress = {
        "done": done,
        "total": total,
        "fraction": progress_fraction(done, total),
        "message": message,
    }
    session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.RUNNING.value)
        .values(progress=progress, heartbeat_at=func.now(), updated_at=func.now())
    )
    session.commit()


def heartbeat(session: Session, job_id: uuid.UUID) -> None:
    session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.RUNNING.value)
        .values(heartbeat_at=func.now())
    )
    session.commit()


def complete(session: Session, job_id: uuid.UUID, result: dict[str, Any] | None = None) -> None:
    """Mark a running job succeeded. Commits."""
    updated = session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.RUNNING.value)
        .values(
            status=JobStatus.SUCCEEDED.value,
            result=result,
            error=None,
            locked_by=None,
            finished_at=func.now(),
            updated_at=func.now(),
        )
        .returning(Job.id)
    ).scalar_one_or_none()
    session.commit()
    if updated is None:
        raise InvalidTransitionError(f"job {job_id} is not running")


def fail(
    session: Session,
    job_id: uuid.UUID,
    error: str,
    *,
    retryable: bool = True,
    defaults: JobDefaults | None = None,
) -> JobStatus:
    """Record a failure. Re-queues with exponential backoff while attempts remain. Commits.

    Returns the resulting status (``queued`` for a scheduled retry, otherwise ``failed``).
    """
    defaults = defaults or get_settings().jobs
    job = session.get(Job, job_id, with_for_update=True, populate_existing=True)
    if job is None or job.status != JobStatus.RUNNING.value:
        session.rollback()
        raise InvalidTransitionError(f"job {job_id} is not running")
    job.error = error[-MAX_ERROR_CHARS:]
    job.locked_by = None
    if retryable and job.attempts < job.max_attempts:
        delay = retry_delay_s(job.attempts, defaults.backoff_base_s, defaults.backoff_max_s)
        job.status = JobStatus.QUEUED.value
        job.run_after = _now() + timedelta(seconds=delay)
        job.heartbeat_at = None
    else:
        job.status = JobStatus.FAILED.value
        job.finished_at = _now()
    status = JobStatus(job.status)
    session.commit()
    return status


def retry(session: Session, job_id: uuid.UUID) -> Job:
    """Manually re-queue a failed or cancelled job with a fresh attempt budget. Commits."""
    job = session.get(Job, job_id, with_for_update=True, populate_existing=True)
    if job is None:
        raise LookupError(job_id)
    if job.status not in (JobStatus.FAILED.value, JobStatus.CANCELLED.value):
        session.rollback()
        raise InvalidTransitionError(
            f"job {job_id} is {job.status}; only failed/cancelled can retry"
        )
    if job.dedupe_key is not None:
        clash = session.scalars(
            select(Job.id).where(
                Job.dedupe_key == job.dedupe_key,
                Job.status.in_((JobStatus.QUEUED.value, JobStatus.RUNNING.value)),
                Job.id != job.id,
            )
        ).first()
        if clash is not None:
            session.rollback()
            raise InvalidTransitionError(f"job {clash} with the same dedupe key is already live")
    job.status = JobStatus.QUEUED.value
    job.attempts = 0
    job.run_after = _now()
    job.finished_at = None
    job.locked_by = None
    job.progress = None
    session.commit()
    session.refresh(job)
    return job


def cancel(session: Session, job_id: uuid.UUID) -> Job:
    """Cancel a queued job. Running jobs are not interrupted in M0. Commits."""
    job = session.get(Job, job_id, with_for_update=True, populate_existing=True)
    if job is None:
        raise LookupError(job_id)
    if job.status != JobStatus.QUEUED.value:
        session.rollback()
        raise InvalidTransitionError(
            f"job {job_id} is {job.status}; only queued jobs can be cancelled"
        )
    job.status = JobStatus.CANCELLED.value
    job.finished_at = _now()
    session.commit()
    session.refresh(job)
    return job


def reap_stale(session: Session, stale_after_s: float) -> int:
    """Re-queue (or fail, if out of attempts) running jobs whose worker stopped heartbeating."""
    cutoff = _now() - timedelta(seconds=stale_after_s)
    stale = session.scalars(
        select(Job)
        .where(Job.status == JobStatus.RUNNING.value, Job.heartbeat_at < cutoff)
        .with_for_update(skip_locked=True)
    ).all()
    for job in stale:
        job.error = f"worker {job.locked_by} stopped heartbeating; reaped"
        job.locked_by = None
        job.heartbeat_at = None
        if job.attempts < job.max_attempts:
            job.status = JobStatus.QUEUED.value
            job.run_after = _now()
        else:
            job.status = JobStatus.FAILED.value
            job.finished_at = _now()
    session.commit()
    return len(stale)
