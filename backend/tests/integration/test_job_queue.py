"""Job queue: enqueue, SKIP LOCKED claim, progress, retry with backoff, reaping (M0)."""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from trailcam.config import JobDefaults
from trailcam.core.types import JobStatus
from trailcam.db.models import Job
from trailcam.pipeline import jobs

pytestmark = pytest.mark.integration

FAST = JobDefaults(max_attempts=3, backoff_base_s=0, backoff_max_s=0)


def _make_runnable(db: Session, job_id: uuid.UUID) -> None:
    db.execute(update(Job).where(Job.id == job_id).values(run_after=datetime.now(UTC)))
    db.commit()


def test_enqueue_claim_complete(db: Session) -> None:
    job = jobs.enqueue(db, "t.a", {"x": 1}).job
    db.commit()
    claimed = jobs.claim(db, "w1")
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == JobStatus.RUNNING
    assert claimed.attempts == 1
    assert claimed.locked_by == "w1"
    assert claimed.started_at is not None
    jobs.complete(db, job.id, {"ok": True})
    done = db.get(Job, job.id, populate_existing=True)
    assert done is not None
    assert done.status == JobStatus.SUCCEEDED
    assert done.result == {"ok": True}
    assert done.finished_at is not None
    assert jobs.claim(db, "w1") is None


def test_claim_respects_priority_type_filter_and_run_after(db: Session) -> None:
    low = jobs.enqueue(db, "t.a", priority=0).job
    high = jobs.enqueue(db, "t.a", priority=10).job
    other = jobs.enqueue(db, "t.b", priority=99).job
    later = jobs.enqueue(
        db, "t.a", priority=50, run_after=datetime.now(UTC) + timedelta(hours=1)
    ).job
    db.commit()
    order = [jobs.claim(db, "w", ["t.a"]) for _ in range(3)]
    assert [j.id if j else None for j in order] == [high.id, low.id, None]
    claimed_other = jobs.claim(db, "w", ["t.b"])
    assert claimed_other is not None
    assert claimed_other.id == other.id
    assert db.get(Job, later.id).status == JobStatus.QUEUED  # type: ignore[union-attr]


def test_concurrent_workers_never_claim_the_same_job(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as s:
        ids = {jobs.enqueue(s, "t.c").job.id for _ in range(40)}
        s.commit()
    claimed: list[uuid.UUID] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker(n: int) -> None:
        barrier.wait()
        with session_factory() as s:
            while (job := jobs.claim(s, f"w{n}")) is not None:
                with lock:
                    claimed.append(job.id)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(claimed) == sorted(ids)  # every job exactly once


def test_progress_is_recorded(db: Session) -> None:
    job = jobs.enqueue(db, "t.p").job
    db.commit()
    jobs.claim(db, "w")
    jobs.report_progress(db, job.id, 3, 12, "frames")
    row = db.get(Job, job.id, populate_existing=True)
    assert row is not None
    assert row.progress == {"done": 3, "total": 12, "fraction": 0.25, "message": "frames"}
    assert row.heartbeat_at is not None


def test_failure_retries_with_backoff_then_fails(db: Session) -> None:
    job = jobs.enqueue(db, "t.r", max_attempts=2).job
    db.commit()
    jobs.claim(db, "w")
    slow = JobDefaults(max_attempts=2, backoff_base_s=60, backoff_max_s=600)
    assert jobs.fail(db, job.id, "first", defaults=slow) is JobStatus.QUEUED
    row = db.get(Job, job.id, populate_existing=True)
    assert row is not None
    assert row.error == "first"
    assert row.run_after > datetime.now(UTC) + timedelta(seconds=50)
    assert jobs.claim(db, "w") is None  # backing off

    _make_runnable(db, job.id)
    again = jobs.claim(db, "w")
    assert again is not None
    assert again.attempts == 2
    assert jobs.fail(db, job.id, "second", defaults=slow) is JobStatus.FAILED
    final = db.get(Job, job.id, populate_existing=True)
    assert final is not None
    assert final.status == JobStatus.FAILED
    assert final.finished_at is not None


def test_non_retryable_failure_fails_immediately(db: Session) -> None:
    job = jobs.enqueue(db, "t.f", max_attempts=5).job
    db.commit()
    jobs.claim(db, "w")
    assert jobs.fail(db, job.id, "fatal", retryable=False, defaults=FAST) is JobStatus.FAILED


def test_manual_retry_and_cancel(db: Session) -> None:
    job = jobs.enqueue(db, "t.m", max_attempts=1).job
    db.commit()
    with pytest.raises(jobs.InvalidTransitionError):
        jobs.retry(db, job.id)  # queued jobs cannot be retried
    jobs.claim(db, "w")
    jobs.fail(db, job.id, "boom", defaults=FAST)
    retried = jobs.retry(db, job.id)
    assert retried.status == JobStatus.QUEUED
    assert retried.attempts == 0
    cancelled = jobs.cancel(db, job.id)
    assert cancelled.status == JobStatus.CANCELLED
    with pytest.raises(jobs.InvalidTransitionError):
        jobs.cancel(db, job.id)
    with pytest.raises(LookupError):
        jobs.retry(db, uuid.uuid4())


def test_complete_requires_running(db: Session) -> None:
    job = jobs.enqueue(db, "t.x").job
    db.commit()
    with pytest.raises(jobs.InvalidTransitionError):
        jobs.complete(db, job.id)
    with pytest.raises(jobs.InvalidTransitionError):
        jobs.fail(db, job.id, "nope")


def test_dedupe_key_makes_enqueue_idempotent(db: Session) -> None:
    key = jobs.stage_key(uuid.uuid4(), "hash", "sha256@1", jobs.config_hash({"a": 1}))
    first = jobs.enqueue(db, "ingest.hash", dedupe_key=key)
    second = jobs.enqueue(db, "ingest.hash", dedupe_key=key)
    db.commit()
    assert first.created
    assert not second.created
    assert second.job.id == first.job.id

    jobs.claim(db, "w")
    jobs.complete(db, first.job.id)
    after_success = jobs.enqueue(db, "ingest.hash", dedupe_key=key)
    assert not after_success.created  # already done for this (target, stage, model, config)
    forced = jobs.enqueue(db, "ingest.hash", dedupe_key=key, force=True)
    db.commit()
    assert forced.created
    assert forced.job.id != first.job.id


def test_config_hash_is_order_independent() -> None:
    assert jobs.config_hash({"a": 1, "b": [1, 2]}) == jobs.config_hash({"b": [1, 2], "a": 1})
    assert jobs.config_hash({"a": 1}) != jobs.config_hash({"a": 2})


def test_reap_stale_requeues_dead_workers_jobs(db: Session) -> None:
    alive = jobs.enqueue(db, "t.s").job
    dead = jobs.enqueue(db, "t.s", max_attempts=1).job
    dead2 = jobs.enqueue(db, "t.s", max_attempts=3).job
    db.commit()
    for _ in range(3):
        jobs.claim(db, "w")
    old = datetime.now(UTC) - timedelta(hours=1)
    db.execute(update(Job).where(Job.id.in_([dead.id, dead2.id])).values(heartbeat_at=old))
    db.commit()
    assert jobs.reap_stale(db, stale_after_s=60) == 2
    status = {
        j.id: j.status
        for j in db.query(Job).populate_existing().filter(Job.id.in_([alive.id, dead.id, dead2.id]))
    }
    assert status == {
        alive.id: JobStatus.RUNNING,
        dead.id: JobStatus.FAILED,  # no attempts left
        dead2.id: JobStatus.QUEUED,
    }
