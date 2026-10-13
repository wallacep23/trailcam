"""Alembic migration covers every DESIGN §8 table and matches the ORM models (M0)."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from trailcam.db.base import Base
from trailcam.db.migrate import alembic_config
from trailcam.db.models import ALL_TABLES

pytestmark = pytest.mark.integration


def _tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version", "spatial_ref_sys"}


def test_all_design_tables_exist(engine: Engine) -> None:
    assert len(ALL_TABLES) == 21
    assert _tables(engine) == set(ALL_TABLES)


def test_extensions_installed(engine: Engine) -> None:
    with engine.connect() as conn:
        names = set(conn.scalars(text("SELECT extname FROM pg_extension")))
    assert {"postgis", "vector"} <= names


def test_migration_matches_models(engine: Engine) -> None:
    """Autogenerate finds nothing to do: models and migration agree."""
    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn,
            opts={
                "compare_type": True,
                "include_object": lambda obj, name, type_, reflected, compare_to: (
                    not (type_ == "table" and name in {"spatial_ref_sys", "alembic_version"})
                ),
            },
        )
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == []


def test_spatial_and_vector_columns(engine: Engine) -> None:
    with engine.connect() as conn:
        types = dict(
            conn.execute(
                text(
                    "SELECT table_name || '.' || column_name, udt_name "
                    "FROM information_schema.columns WHERE table_schema = 'public' "
                    "AND udt_name IN ('geography', 'vector')"
                )
            )
            .tuples()
            .all()
        )
    assert types == {
        "property.boundary": "geography",
        "property.centroid": "geography",
        "site.location": "geography",
        "site.scene_fingerprint": "vector",
        "embedding.vector": "vector",
    }


def test_enum_check_constraints_reject_bad_values(engine: Engine) -> None:
    with engine.connect() as conn, pytest.raises(IntegrityError, match="ck_job_status_valid"):
        conn.execute(
            text("INSERT INTO job (id, type, status) VALUES (gen_random_uuid(), 't', 'bogus')")
        )


def test_downgrade_then_upgrade_round_trip(engine: Engine, database_url: str) -> None:
    cfg = alembic_config(database_url)
    command.downgrade(cfg, "base")
    try:
        assert _tables(engine) == set()
    finally:
        command.upgrade(cfg, "head")
    assert _tables(engine) == set(ALL_TABLES)
