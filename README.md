# Trail Camera Analyzer (`trailcam`)

Local-first app that ingests trail-camera videos and photos, detects and classifies deer, and turns
sightings into effort-normalized movement patterns for planning hunts. The full design is in
[`docs/DESIGN.md`](docs/DESIGN.md); decisions are in [`docs/adr/`](docs/adr/).

**Status: M0 — Foundations.** Database schema, job queue, worker, API, web shell, CI. Ingest and
the vision pipeline arrive in M1–M3 (see DESIGN §17 and [`docs/plans/`](docs/plans/)).

```
apps/web/         React + TypeScript UI (Vite). src/api/ is GENERATED — do not edit.
backend/          Python package `trailcam` (FastAPI API, worker, Alembic migrations, tests)
  src/trailcam/core/      pure domain logic (no I/O)        pipeline/  job queue, worker, stages
  src/trailcam/db/        models, sessions, migrate          api/       HTTP API
docker/db/        PostgreSQL 16 + PostGIS + pgvector image
models/           registry.yaml (every model + its license); weights/ is gitignored
scripts/          dev_seed, export_openapi, gen_api_client, smoke_test, check_licenses
```

## Run everything with Docker (Windows, macOS, Linux)

Requires Docker Desktop (WSL2 backend on Windows).

```powershell
copy .env.example .env          # then set TRAILCAM_MEDIA_HOST_DIR to your media folder
docker compose up --build -d    # db, migrate (backup + schema), api, worker, web
python scripts/smoke_test.py    # health + a job that fails once, retries and succeeds
docker compose exec api python /app/scripts/dev_seed.py   # optional: a starting property (no sites)
```

- Web UI: <http://localhost:5173> (the **Jobs** screen is live in M0; others show their milestone)
- API docs: <http://localhost:8000/api/v1/docs>
- Logs: `docker compose logs -f api worker` (one JSON object per line)
- Stop: `docker compose down` (add `-v` to also delete the database volume)

Property, site and camera names are always yours: sites and their aliases are created on the
Setup screen (M1), never hard-coded. The seed only creates a starting property whose name,
timezone and centroid come from `TRAILCAM_PROPERTY_DEFAULTS__*` settings.

Your media folder is mounted **read-only** at `/media`; the app cannot modify it.
Database backups are written to `./backups` before every schema migration.
GPU for the worker (needed from M2): `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`.

## Develop natively (faster reload)

Requires [uv](https://docs.astral.sh/uv/), Node 20+ and pnpm. Keep the database in Docker:

```powershell
docker compose up -d db
cd backend
uv sync                                   # Python 3.12 venv with dev tools
$env:TRAILCAM_DATABASE_URL = "postgresql+psycopg://trailcam:trailcam@localhost:5432/trailcam"
uv run trailcam-migrate
uv run uvicorn --factory trailcam.api.main:app_factory --reload       # API on :8000
uv run trailcam-worker                                                  # in a second terminal

cd ..\apps\web
pnpm install
pnpm dev                                  # UI on :5173, proxies /api to :8000
```

## Checks (the same ones CI runs)

```powershell
# backend (from backend/)
uv run ruff check . ; uv run ruff format --check . ; uv run mypy
$env:TRAILCAM_TEST_DATABASE_URL = "postgresql+psycopg://trailcam:trailcam@localhost:5432/trailcam_test"
uv run pytest --cov                       # unit + integration (integration needs the db)

# web (from apps/web/)
pnpm lint ; pnpm typecheck ; pnpm test ; pnpm build

# generated API client is current (from the repo root)
pnpm --dir apps/web check:api             # `gen:api` regenerates it after API changes
uv run --project backend python scripts/check_licenses.py
```

Integration tests truncate every table in the test database; never point
`TRAILCAM_TEST_DATABASE_URL` at data you care about. The compose `db` creates `trailcam_test`.

## Configuration

All settings are environment variables prefixed `TRAILCAM_` (or a `.env` file); see
[`backend/src/trailcam/config.py`](backend/src/trailcam/config.py). Nested settings use `__`,
e.g. `TRAILCAM_JOBS__MAX_ATTEMPTS=5`, `TRAILCAM_WORKER__POLL_INTERVAL_S=0.5`.
