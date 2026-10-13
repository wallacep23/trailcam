# ADR 0001 — Technology stack

- Status: accepted (M0, 2026-10-12)
- Context: DESIGN §6, §18; NFR-1, NFR-7, NFR-9, NFR-10

## Decision

| Layer | Choice |
| --- | --- |
| Backend | Python 3.12, FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2.0 (sync, psycopg 3), Alembic |
| Worker | Same package and image as the API, separate process (`trailcam-worker`) |
| Database | PostgreSQL 16 + PostGIS 3.5 + pgvector (ADR 0002) |
| Queue | Postgres `job` table with `FOR UPDATE SKIP LOCKED` (ADR 0003) |
| Frontend | React 18 + TypeScript (strict) + Vite, TanStack Query, Zustand, Tailwind CSS 4 |
| API client | `openapi-typescript` types + `openapi-fetch`, generated into `apps/web/src/api/` |
| Tooling | uv, pnpm, ruff, mypy (strict on `core/`), pytest, eslint, vitest, GitHub Actions |
| Packaging | Docker Compose (db, migrate, api, worker, web); native uv + pnpm for development |

## Notes and consequences

- **Sync SQLAlchemy.** Endpoints are plain `def` (FastAPI runs them in a thread pool) and the worker
  is synchronous. The workload is GPU/decode-bound, not request-bound, so async adds complexity for
  no gain. Revisit only if the API becomes latency-bound under many concurrent clients.
- **SQLAlchemy pinned `<2.1`.** GeoAlchemy2 0.17 is not yet compatible with SQLAlchemy 2.1.
- **Structured logging uses the standard library** (`trailcam.log`) with a JSON formatter and
  context variables, rather than adding structlog. Fewer dependencies; the same JSON lines.
- **UUIDv7** is generated in Python (`core/ids.py`) because Postgres 16 has no `uuidv7()`.
- **Routing in the web app** is a ten-line hash router until a screen needs nested routes.
- **Licenses (NFR-7).** Our code, Python packages and models must be MIT/Apache-2.0/BSD, enforced
  by `scripts/check_licenses.py` in CI. Two reviewed exceptions:
  - *psycopg 3* is LGPL-3.0. It is used unmodified as an imported library, which LGPL permits in
    proprietary software. If legal review objects, `pg8000` (BSD-3) is a drop-in SQLAlchemy driver.
  - *PostGIS* is GPL-2.0, but it runs inside the separate PostgreSQL server process; nothing is
    linked into our code. Re-check before distributing a bundled installer (M7).
- **Python version.** The containers use 3.12 as the design requires; the code also runs on 3.13.
