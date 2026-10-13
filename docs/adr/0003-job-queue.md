# ADR 0003 — Postgres-backed job queue

- Status: accepted (M0, 2026-10-12)
- Context: DESIGN §6 ("procrastinate, or a minimal jobs table with SKIP LOCKED"), §9.2, NFR-11

## Decision

A minimal queue on the `job` table (`trailcam.pipeline.jobs`), not procrastinate:

- **Claim:** `UPDATE job … WHERE id = (SELECT id … WHERE status='queued' AND run_after <= now()
  ORDER BY priority DESC, run_after, id LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING id`. Any number
  of workers can poll safely; a test runs 8 concurrent workers over 40 jobs and checks each job is
  claimed exactly once.
- **Retry:** a failing handler re-queues the job with exponential backoff
  (`backoff_base_s * 2^(attempt-1)`, capped) until `max_attempts`, then marks it `failed`.
  Handlers raise `FatalJobError` to fail immediately. Failed/cancelled jobs can be re-queued from
  the API (`POST /jobs/{id}/retry`).
- **Progress:** `{done, total, fraction, message}` in `job.progress`, shown on the Jobs page.
- **Crash safety:** a heartbeat thread refreshes `heartbeat_at` while a handler runs; the worker
  re-queues `running` jobs whose heartbeat is older than `stale_after_s` (counted as an attempt).
- **Idempotency:** optional `dedupe_key`, normally `stage_key(target, stage, model_version,
  config_hash)` (CLAUDE.md). A partial unique index allows only one *live* (queued/running) job
  per key; enqueueing a key that already succeeded returns that job unless `force=True`.
- **Handlers** register with `@job_handler("type")`; M0 ships `system.selftest`.

## Why not procrastinate

It would work, but brings its own schema, migrations and async runtime. Our needs (claim, retry,
progress, dedupe, re-run per deployment) fit in ~250 lines that we fully control and test, and
jobs stay transactional with the data they produce. Revisit if we need scheduling/cron, job
dependencies or LISTEN/NOTIFY wake-ups (polling every second is fine for a local app).
