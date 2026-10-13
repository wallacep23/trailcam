# ADR 0004 — Development environment and packaging

- Status: accepted (M0, 2026-10-12)
- Context: DESIGN §6, NFR-1, NFR-10

## Decision

- **`docker compose up --build`** is the one-command way to run everything: `db`, a one-shot
  `migrate` (backup + `alembic upgrade head`), `api` (uvicorn), `worker`, and `web` (Vite build
  served by nginx, which proxies `/api` to the API). Web UI on <http://localhost:5173>.
- **Media is mounted read-only** (`${TRAILCAM_MEDIA_HOST_DIR}:/media:ro`), so the guardrail
  "never modify user media" is enforced by the OS, not only by code (FR-ING-5).
- **GPU is opt-in** through `docker-compose.gpu.yml` so the default stack also runs on machines
  without an NVIDIA runtime (NFR-1 CPU fallback). The worker needs the GPU from M2.
- **Native development** uses `uv` (backend) and `pnpm` (web) against the compose `db`:
  hot reload is faster than rebuilding images, and Windows bind-mount file watching is unreliable.
- **Lockfiles** (`backend/uv.lock`, `apps/web/pnpm-lock.yaml`) are committed; Docker and CI install
  with `--frozen` so builds are reproducible.
- **Line endings** are LF via `.gitattributes`, so shell and SQL files work in Linux containers
  when the repo is checked out on Windows.
- **The generated client** (`apps/web/openapi.json`, `apps/web/src/api/schema.d.ts`) is committed;
  `pnpm --dir apps/web gen:api` regenerates it, and CI (`check:api`) plus the backend unit test
  `test_committed_openapi_is_up_to_date` fail when it is stale.
