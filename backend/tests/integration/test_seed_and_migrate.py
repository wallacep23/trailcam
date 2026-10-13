"""``scripts/dev_seed.py`` is idempotent; ``trailcam-migrate`` backs up before upgrading."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from trailcam.db import migrate
from trailcam.db.models import Job, Property, Site

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[3]


def _load_seed() -> ModuleType:
    spec = importlib.util.spec_from_file_location("dev_seed", REPO / "scripts" / "dev_seed.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["dev_seed"] = module
    spec.loader.exec_module(module)
    return module


def test_dev_seed_is_idempotent(session_factory: sessionmaker[Session]) -> None:
    seed = _load_seed()
    with session_factory() as s:
        first = seed.seed(s, with_selftest=True)
        s.commit()
    with session_factory() as s:
        second = seed.seed(s, with_selftest=True)
        s.commit()
    assert first == {"property": 1, "job": 1}
    assert second == {"property": 0, "job": 0}
    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(Property)) == 1
        assert s.scalar(select(func.count()).select_from(Site)) == 0  # sites are user-created
        assert s.scalar(select(func.count()).select_from(Job)) == 1
        prop = s.scalars(select(Property)).one()
        assert prop.tz == "America/Detroit"


def test_migrate_is_noop_at_head(database_url: str, tmp_path: Path) -> None:
    assert migrate.upgrade(database_url, tmp_path) == "0001"
    assert list(tmp_path.iterdir()) == []  # nothing pending -> no backup taken
    assert migrate.main(["--check"]) == 0


@pytest.mark.skipif(shutil.which("pg_dump") is None, reason="pg_dump not installed")
def test_backup_database_writes_dump(database_url: str, tmp_path: Path) -> None:
    target = migrate.backup_database(database_url, tmp_path, label="test")
    assert target is not None
    assert target.exists()
    assert target.stat().st_size > 0
    assert target.read_bytes()[:5] == b"PGDMP"
