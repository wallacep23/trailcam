"""Jobs API (DESIGN §15 "Jobs & models"; NFR-11 jobs page)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from trailcam.api.deps import DbSession
from trailcam.api.schemas import ErrorOut, JobCreate, JobOut, JobPage, JobStats, JobTypeOut
from trailcam.core.types import JobStatus
from trailcam.db.models import Job
from trailcam.pipeline import jobs as queue
from trailcam.pipeline.registry import load_handlers

router = APIRouter(prefix="/jobs", tags=["jobs"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorOut}}
_CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": ErrorOut}}


def _get_or_404(db: DbSession, job_id: uuid.UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} not found")
    return job


@router.get("", response_model=JobPage)
def list_jobs(
    db: DbSession,
    status_: Annotated[list[JobStatus] | None, Query(alias="status")] = None,
    type_: Annotated[str | None, Query(alias="type")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobPage:
    """Newest first. Filter by one or more statuses and/or a job type."""
    query = select(Job)
    if status_:
        query = query.where(Job.status.in_([s.value for s in status_]))
    if type_:
        query = query.where(Job.type == type_)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit).offset(offset)
    )
    return JobPage(
        items=[JobOut.model_validate(j) for j in rows], total=total, limit=limit, offset=offset
    )


@router.get("/stats", response_model=JobStats)
def job_stats(db: DbSession) -> JobStats:
    counts = {s: 0 for s in JobStatus}
    for st, n in db.execute(select(Job.status, func.count()).group_by(Job.status)).tuples():
        counts[JobStatus(st)] = n
    return JobStats(counts=counts)


@router.get("/types", response_model=list[JobTypeOut])
def job_types() -> list[JobTypeOut]:
    return [
        JobTypeOut(type=s.job_type, description=s.description, user_runnable=s.user_runnable)
        for s in sorted(load_handlers().values(), key=lambda s: s.job_type)
    ]


@router.post(
    "",
    response_model=JobOut,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorOut}},
)
def create_job(body: JobCreate, db: DbSession) -> JobOut:
    """Enqueue a user-runnable job (in M0: ``system.selftest``)."""
    spec = load_handlers().get(body.type)
    if spec is None or not spec.user_runnable:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"job type {body.type!r} is not user-runnable"
        )
    result = queue.enqueue(
        db, body.type, body.payload, priority=body.priority, max_attempts=body.max_attempts
    )
    db.commit()
    return JobOut.model_validate(result.job)


@router.get("/{job_id}", response_model=JobOut, responses=_NOT_FOUND)
def get_job(job_id: uuid.UUID, db: DbSession) -> JobOut:
    return JobOut.model_validate(_get_or_404(db, job_id))


@router.post("/{job_id}/retry", response_model=JobOut, responses={**_NOT_FOUND, **_CONFLICT})
def retry_job(job_id: uuid.UUID, db: DbSession) -> JobOut:
    """Re-queue a failed or cancelled job with a fresh attempt budget."""
    _get_or_404(db, job_id)
    try:
        job = queue.retry(db, job_id)
    except queue.InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return JobOut.model_validate(job)


@router.post("/{job_id}/cancel", response_model=JobOut, responses={**_NOT_FOUND, **_CONFLICT})
def cancel_job(job_id: uuid.UUID, db: DbSession) -> JobOut:
    """Cancel a queued job."""
    _get_or_404(db, job_id)
    try:
        job = queue.cancel(db, job_id)
    except queue.InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return JobOut.model_validate(job)
