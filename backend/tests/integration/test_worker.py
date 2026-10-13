"""Worker runs registered handlers end to end (M0: system.selftest)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from trailcam.config import Settings
from trailcam.core.types import JobStatus
from trailcam.db.models import Job
from trailcam.pipeline import jobs
from trailcam.pipeline.registry import HandlerSpec, JobContext
from trailcam.pipeline.runner import Worker

pytestmark = pytest.mark.integration


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("TRAILCAM_JOBS__BACKOFF_BASE_S", "0")
    monkeypatch.setenv("TRAILCAM_WORKER__HEARTBEAT_INTERVAL_S", "0.05")
    return Settings(_env_file=None)


def _worker(factory: sessionmaker[Session], settings: Settings, **kw: object) -> Worker:
    return Worker(session_factory=factory, settings=settings, worker_id="test-worker", **kw)  # type: ignore[arg-type]


def test_selftest_succeeds_with_progress(
    session_factory: sessionmaker[Session], settings: Settings
) -> None:
    with session_factory() as s:
        job_id = jobs.enqueue(s, "system.selftest", {"steps": 4, "sleep_s": 0}).job.id
        s.commit()
    assert _worker(session_factory, settings).run_once() is JobStatus.SUCCEEDED
    with session_factory() as s:
        job = s.get(Job, job_id)
        assert job is not None
        assert job.status == JobStatus.SUCCEEDED
        assert job.progress == {"done": 4, "total": 4, "fraction": 1.0, "message": "step 4 of 4"}
        assert job.result == {"steps": 4, "attempt": 1}


def test_selftest_retries_then_succeeds(
    session_factory: sessionmaker[Session], settings: Settings
) -> None:
    with session_factory() as s:
        job_id = jobs.enqueue(
            s, "system.selftest", {"steps": 1, "sleep_s": 0, "fail_times": 2}, max_attempts=3
        ).job.id
        s.commit()
    worker = _worker(session_factory, settings)
    assert worker.run_once() is JobStatus.QUEUED
    assert worker.run_once() is JobStatus.QUEUED
    assert worker.run_once() is JobStatus.SUCCEEDED
    with session_factory() as s:
        job = s.get(Job, job_id)
        assert job is not None
        assert job.attempts == 3
        assert job.error is None


def test_fatal_error_is_not_retried(
    session_factory: sessionmaker[Session], settings: Settings
) -> None:
    with session_factory() as s:
        job_id = jobs.enqueue(s, "system.selftest", {"fatal": True}, max_attempts=5).job.id
        s.commit()
    assert _worker(session_factory, settings).run_once() is JobStatus.FAILED
    with session_factory() as s:
        job = s.get(Job, job_id)
        assert job is not None
        assert job.attempts == 1
        assert "FatalJobError" in (job.error or "")


def test_worker_ignores_types_it_cannot_handle(
    session_factory: sessionmaker[Session], settings: Settings
) -> None:
    with session_factory() as s:
        jobs.enqueue(s, "unknown.type")
        s.commit()
    assert _worker(session_factory, settings).run_once() is None


def test_heartbeat_runs_during_long_handlers(
    session_factory: sessionmaker[Session], settings: Settings
) -> None:
    beats: list[object] = []

    def slow(ctx: JobContext) -> dict[str, object]:
        import time

        time.sleep(0.3)
        with ctx.session_factory() as s:
            beats.append(s.get(Job, ctx.job_id).heartbeat_at)  # type: ignore[union-attr]
        return {}

    handlers = {"t.slow": HandlerSpec("t.slow", slow, "", False)}
    with session_factory() as s:
        jobs.enqueue(s, "t.slow")
        s.commit()
        started = s.query(Job).one().created_at
    assert _worker(session_factory, settings, handlers=handlers).run_once() is JobStatus.SUCCEEDED
    assert beats
    assert beats[0] is not None
    assert beats[0] > started  # type: ignore[operator]


def test_run_forever_stops_on_event(
    session_factory: sessionmaker[Session], settings: Settings
) -> None:
    import threading

    worker = _worker(session_factory, settings)
    with session_factory() as s:
        job_id = jobs.enqueue(s, "system.selftest", {"steps": 1, "sleep_s": 0}).job.id
        s.commit()
    thread = threading.Thread(target=worker.run_forever)
    thread.start()
    for _ in range(100):
        with session_factory() as s:
            if s.get(Job, job_id).status == JobStatus.SUCCEEDED:  # type: ignore[union-attr]
                break
        threading.Event().wait(0.05)
    worker.stop_event.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    with session_factory() as s:
        assert s.get(Job, job_id).status == JobStatus.SUCCEEDED  # type: ignore[union-attr]
