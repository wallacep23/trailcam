# ADR 0002 — Database and schema conventions

- Status: accepted (M0, 2026-10-12)
- Context: DESIGN §8, NFR-4, NFR-5

## Decision

PostgreSQL 16 is the single source of truth, with **PostGIS** for site/property geometry and
**pgvector** for embeddings and scene fingerprints. The `db` image is `pgvector/pgvector:0.8.0-pg16`
plus PostGIS 3 from the PostgreSQL apt repository (`postgresql-16-postgis-3`). (The
`postgis/postgis:16` images are built on Debian bullseye, whose PostgreSQL apt repo is archived.) All 21 tables of DESIGN §8 are created by Alembic
revision `0001_initial_schema`, which also runs `CREATE EXTENSION IF NOT EXISTS postgis, vector`.

Conventions:

1. **Ids** are UUIDv7 (time-ordered) generated in Python.
2. **Timestamps** are `timestamptz`, stored in UTC; the property timezone is for display only.
3. **Enumerations** are `text` columns with `CHECK (col IN (...))` constraints generated from the
   `StrEnum`s in `trailcam.core.types`, not native Postgres enums: adding a value is a one-line
   migration that rewrites a constraint, instead of `ALTER TYPE` (which cannot run in a transaction
   on older servers and is awkward to downgrade).
4. **Provenance.** Every derived row has `produced_by jsonb NOT NULL`
   (`{stage, model, version, config_hash}`) so any stage can be re-run per deployment (NFR-5).
5. **Constraint names** follow a fixed naming convention so migrations are deterministic.
6. **Geography** columns use SRID 4326 with explicit GiST indexes.
7. **Embeddings** use an un-dimensioned `vector` column plus a `dim` column, because the embedding
   model (and so the dimension) is configurable (DESIGN §6). pgvector HNSW indexes need a fixed
   dimension, so they will be created per model as partial expression indexes, e.g.
   `CREATE INDEX … USING hnsw ((vector::vector(768)) vector_cosine_ops) WHERE model = 'megadescriptor-l'`,
   in the migration that introduces each model (M5).
8. **Labels are append-only** (`label.supersedes_id`); "latest human wins" is a query, never an
   update. Models never write over human labels (CLAUDE.md guardrail).
9. **Media identity** is `sha256` (unique); `(deployment_id, path)` is unique so re-scanning a
   folder is idempotent (FR-ING-4, FR-ING-6).
10. **Additions to §8**, all needed by the design's own requirements: `property.centroid`
    (weather/sun until a boundary exists), `site.last_heading_deg` (default heading, §9.1),
    `deployment.clock_offset_s` (§9.3), job-queue bookkeeping columns (ADR 0003),
    `created_at`/`updated_at` audit columns.

## Safety

`trailcam-migrate` (the compose `migrate` service) runs `pg_dump -Fc` into `./backups` before
applying pending migrations to a database that already has a schema (NFR-4). The integration test
`test_migration_matches_models` fails if the ORM models and the migrations drift apart, and
`test_downgrade_then_upgrade_round_trip` keeps downgrades working.
