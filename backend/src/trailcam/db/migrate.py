"""Run Alembic migrations, backing up the database first (NFR-4).

``trailcam-migrate`` (or ``python -m trailcam.db.migrate``) is what the ``migrate`` service in
``docker-compose.yml`` runs before the API and worker start. If the database already has a schema
and there are pending migrations, ``pg_dump`` writes a custom-format backup to
``TRAILCAM_BACKUP_DIR`` before upgrading. A fresh, empty database needs no backup.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, make_url

from trailcam.config import get_settings
from trailcam.log import configure_logging

log = logging.getLogger("trailcam.migrate")

BACKEND_DIR = Path(__file__).resolve().parents[3]


def alembic_config(database_url: str | None = None) -> Config:
    """Alembic config that works from any working directory."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    if database_url:
        cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def schema_state(database_url: str) -> tuple[str | None, str]:
    """Return ``(current_revision, head_revision)``."""
    script = ScriptDirectory.from_config(alembic_config(database_url))
    head = script.get_current_head()
    if head is None:
        raise RuntimeError("no Alembic head revision found")
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
    return current, head


def pg_dump_url(database_url: str) -> str:
    """libpq URL for ``pg_dump`` (drops the ``+psycopg`` driver suffix)."""
    url = make_url(database_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


def backup_database(database_url: str, backup_dir: Path, label: str) -> Path | None:
    """Write a ``pg_dump -Fc`` backup. Returns the file, or ``None`` if pg_dump is unavailable."""
    pg_dump = shutil.which("pg_dump")
    if pg_dump is None:
        log.warning("pg_dump not found; skipping pre-migration backup")
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"trailcam-{stamp}-before-{label}.dump"
    subprocess.run(  # noqa: S603 - fixed executable and arguments
        [pg_dump, "--format=custom", "--no-owner", f"--file={target}", pg_dump_url(database_url)],
        check=True,
    )
    log.info("database backed up", extra={"backup": str(target)})
    return target


def upgrade(database_url: str, backup_dir: Path, *, backup: bool = True) -> str:
    current, head = schema_state(database_url)
    if current == head:
        log.info("schema up to date", extra={"revision": head})
        return head
    if backup and current is not None:
        backup_database(database_url, backup_dir, label=head)
    log.info("upgrading schema", extra={"from": current, "to": head})
    command.upgrade(alembic_config(database_url), "head")
    return head


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up, then migrate the trailcam database.")
    parser.add_argument("--no-backup", action="store_true", help="skip the pre-migration backup")
    parser.add_argument("--check", action="store_true", help="exit 1 if migrations are pending")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if args.check:
        current, head = schema_state(settings.database_url)
        log.info("schema state", extra={"current": current, "head": head})
        return 0 if current == head else 1
    upgrade(settings.database_url, settings.backup_dir, backup=not args.no_backup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
