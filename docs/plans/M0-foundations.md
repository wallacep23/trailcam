# M0 — Foundations: implementation plan

**Status: done (2026-10-12).** All acceptance criteria verified on the owner's Windows PC; see
"Verification" at the end.

Source: `docs/DESIGN.md` §17 (M0), with §6 (stack), §7 (repo skeleton), §8 (data model),
§15 (API), §16.3 (tests) and §18 (agent instructions).

## Goal

A runnable, empty-but-real system: the monorepo, the database schema for every §8 table, a
transactional job queue with a worker, a thin API, a web shell that talks to the API through a
generated TypeScript client, CI, and the decision records. No ML and no ingest logic yet (M1+).

## M0 checklist (from the design) and how each item is met

| # | Design item | Deliverable | Verified by |
|---|---|---|---|
| 1 | Monorepo per §7; `docker compose up` brings up db (PostGIS + pgvector), api, worker, web | Folder layout from §7; `docker-compose.yml` with `db`, `migrate`, `api`, `worker`, `web`; `docker/db/Dockerfile` = `postgis/postgis:16` + `postgresql-16-pgvector`; healthchecks + `depends_on` conditions | `docker compose config`; CI job `compose-smoke` runs `docker compose up --build --wait` and curls `/api/v1/health`; local native run of the same commands |
| 2 | Alembic migration for all §8 tables; `scripts/dev_seed.py` | `backend/alembic/versions/0001_initial_schema.py` creating extensions `postgis`, `vector` and all 21 tables; `scripts/dev_seed.py` seeds a starting property (from settings) and optionally a self-test job, idempotently; it never creates sites | Integration tests: upgrade → every §8 table/column exists → downgrade → upgrade; ORM metadata matches the migration (autogenerate diff is empty); seed twice → no duplicates |
| 3 | Pydantic settings; structured logging; job queue with retry and progress | `trailcam/config.py` (`TRAILCAM_*` env); `trailcam/logging.py` (JSON lines, request/job context); `pipeline/jobs.py` (enqueue with dedupe key, `SKIP LOCKED` claim, progress, heartbeat, retry with backoff, stale-lock reaping, manual retry); `pipeline/runner.py` worker with handler registry and graceful shutdown; `system.selftest` job type | Unit tests (backoff, settings, log format); integration tests (claim exclusivity across two connections, retry→success, retry exhaustion→failed, progress, stale reaping, dedupe); live run: worker processes a self-test job queued through the API |
| 4 | OpenAPI → TS client generation wired; CI running lint, types and tests | `scripts/export_openapi.py` (no server needed) → `apps/web/openapi.json` → `openapi-typescript` → `apps/web/src/api/schema.d.ts`; `openapi-fetch` wrapper in `src/lib/api.ts`; `.github/workflows/ci.yml` with backend (ruff, mypy, pytest + Postgres), web (eslint, tsc, vitest, build), API-client drift check, model-license check, compose smoke | Generated client type-checks against the web code; CI file validated; drift check script runs locally |
| 5 | `CLAUDE.md`, `docs/DESIGN.md`, first ADRs (stack, DB, queue) | `CLAUDE.md` (existing §18 text + repo commands), `docs/DESIGN.md`, `docs/adr/0001-tech-stack.md`, `0002-database-and-schema.md`, `0003-job-queue.md`, `0004-dev-environment-and-packaging.md` | Files present and consistent with the code |

## Acceptance criteria for M0

1. `docker compose up` brings up `db`, `api`, `worker`, `web`; the API health endpoint reports the
   database reachable with PostGIS and pgvector installed and the schema at head.
2. `alembic upgrade head` on an empty database creates every §8 table; `downgrade base` removes
   them cleanly; ORM models and migration agree.
3. `scripts/dev_seed.py` is idempotent.
4. A job enqueued through the API is picked up by the worker, reports progress, retries on
   failure with backoff, and ends `succeeded` or `failed`; a failed job can be retried via the API.
5. The TS client is generated from the API's OpenAPI document, and the web app compiles against it.
6. Lint (ruff, eslint), types (mypy strict on `core/`, mypy on the rest, `tsc --noEmit`) and tests
   (pytest unit + integration, vitest) pass; CI runs all of them.
7. Guardrails hold: `core/` has no I/O or framework imports (enforced by a test); source media is
   never touched (nothing in M0 opens media).

## Out of scope for M0

Ingest stages, folder parsing, importers, models, review UI, analytics (M1+). Screens other than
Jobs are placeholders that name the milestone that delivers them.

## Work order

1. Plan (this file).
2. Backend: settings → logging → `core/ids.py` (UUIDv7) → ORM models → Alembic migration →
   job queue → worker → API (health, jobs, properties) → seed → tests.
3. Web: Vite/React/TS shell, feature folders, Jobs page, generated client.
4. Compose, Dockerfiles, CI, ADRs, README.
5. Verify every acceptance criterion; independent review; fix; deliver.

## Verification (2026-10-12, Windows 10 + Docker Desktop 4.95, Python 3.12.11, Node 24)

| # | Criterion | Result |
|---|---|---|
| 1 | `docker compose up --build -d` | db healthy, migrate exited 0, api healthy, worker running, web serving on :5173. `/api/v1/health` = `ok` (database, postgis, vector, schema 0001 at head) |
| 2 | Migration | `alembic check` reports no drift; integration tests cover all 21 tables, geography/vector columns, CHECK constraints, downgrade→upgrade round trip |
| 3 | Seed | `dev_seed.py` twice in the api container: `{property: 1}` then `{property: 0}` (no sites: sites are user-created, FR-SITE-2) |
| 4 | Queue end to end | `scripts/smoke_test.py` through the nginx proxy: self-test failed attempt 1, backed off 5 s, succeeded on attempt 2 with progress 100%; same flow clicked through the Jobs screen. Worker logs are JSON lines with job context. Pre-migration `pg_dump` works in the container |
| 5 | Generated client | `openapi-typescript` 7.13 output committed; `pnpm check:api` up to date; web type-checks against it |
| 6 | Lint/types/tests | ruff + format clean; mypy clean (strict on `core/`) incl. tests and scripts; pytest 72 passed, 1 skipped (pg_dump not on the Windows host; covered in-container), coverage 92% total; eslint, `tsc`, vitest 7/7, `vite build` OK; license check OK |
| 7 | Guardrails | `test_core_purity` enforces no I/O/framework imports in `core/`; media mounted `:ro` |

Not verifiable locally: the GitHub Actions workflow itself (no remote yet). Its steps are the same
commands listed above.
