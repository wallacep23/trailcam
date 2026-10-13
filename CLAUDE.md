# CLAUDE.md — instructions for coding agents

Design: `docs/DESIGN.md` (section 18 is the source of the rules below). Decisions: `docs/adr/`.
Milestone plans: `docs/plans/`. Current milestone: **M0 done → M1 (ingest and legacy import)**.

**Repo commands**

- Stack: `docker compose up --build -d`, then `python scripts/smoke_test.py`.
- Backend (in `backend/`): `uv sync`; `uv run ruff check . && uv run ruff format --check .`;
  `uv run mypy`; `uv run pytest` (integration tests need `TRAILCAM_TEST_DATABASE_URL`, e.g.
  `postgresql+psycopg://trailcam:trailcam@localhost:5432/trailcam_test` with `docker compose up -d db`).
- New migration: edit `trailcam/db/models.py`, then
  `uv run alembic revision --autogenerate -m "..."`, review it, and keep
  `test_migration_matches_models` green.
- Web (in `apps/web/`): `pnpm install`; `pnpm lint`; `pnpm typecheck`; `pnpm test`; `pnpm build`.
- After any API change: `pnpm --dir apps/web gen:api` and commit `openapi.json` + `src/api/schema.d.ts`.
- New pipeline stage: a pure function in `core/` + a `@job_handler` in `pipeline/stages/`, enqueued
  with `dedupe_key=stage_key(target, stage, model_version, config_hash(cfg))`.

**Context**

- The owner is a capable developer on Windows with an RTX 3070. The property ("Judy's") is near South Lyon, Michigan, centered at 42.493, -83.665 (America/Detroit).
- Media lives at `C:\Users\pwall\Desktop\TrailCamera\Judy's\`. The legacy app is at `C:\Users\pwall\Desktop\Code\TrailcamParser\` (reference only: reuse its hotkey scheme and watermark-OCR idea, not its code).
- The repo lives at `C:\Users\pwall\Desktop\trailcam\` (GitHub: `wallacep23/trailcam`).

**Order of work**

1. Build M0 completely before any ML. Get the skeleton, schema, queue and CI green.
2. In M1, write `core/` functions test-first. The real folder names and legacy counts in section 12 are ready-made test cases.
3. Before M2, ask the owner for 10–20 short fixture clips covering: empty/wind, single buck day, single buck IR night, doe + fawns, foggy lens, turkey, person.
4. Do not start M4+ until the M2 and M3 gates in section 16 pass on the golden split.

**Guardrails (non-negotiable)**

- Never write, rename, move or delete anything inside media folders. Read-only. The legacy app renamed files; this one must not.
- Never treat an all-zero legacy entry as a negative label.
- Never overwrite a human label with a model output.
- Never compute analytics from raw clip counts. Use events / effort.
- Never let an AGPL or non-commercial model or dataset into the shipped path. Record the license in `models/registry.yaml` before first use.
- Never hand-edit `apps/web/src/api/` (generated).
- Keep `core/` free of I/O, DB, GPU and framework imports.

**Conventions**

- Python 3.12, `uv`, ruff (line length 100), mypy strict for `core/`, pytest. Type hints everywhere; dataclasses or Pydantic for domain types.
- TypeScript strict, React function components, TanStack Query for server state, feature folders.
- Each pipeline stage is a pure function over inputs plus a thin job wrapper. It must be idempotent and keyed by `(target, stage, model_version, config_hash)`.
- Requirement IDs (`FR-ING-3`) go in test names and commit messages.
- Small PR-sized commits; conventional commit messages.
- Record each significant decision as an ADR in `docs/adr/NNNN-title.md`.
- When unsure about domain behaviour (deer biology, hunting practice), make it configurable with a sensible default and note it in the ADR rather than hard-coding.

**Definition of done for any feature:** code + tests + types pass, the requirement ID is referenced, the docs are updated if behaviour changed, and a demo works on real `Judy's` data.