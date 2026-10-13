"""Health endpoint: API up, database reachable, extensions installed, schema at head."""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from trailcam.api.deps import DbSession
from trailcam.api.schemas import Health, HealthCheck
from trailcam.db.migrate import alembic_config

router = APIRouter(tags=["health"])
log = logging.getLogger("trailcam.api.health")

REQUIRED_EXTENSIONS = ("postgis", "vector")


def _app_version() -> str:
    try:
        return version("trailcam")
    except PackageNotFoundError:
        return "0.0.0+local"


def _schema_head() -> str | None:
    try:
        return ScriptDirectory.from_config(alembic_config()).get_current_head()
    except Exception:  # pragma: no cover - only if the alembic folder is missing
        log.warning("could not read alembic head", exc_info=True)
        return None


@router.get(
    "/health",
    response_model=Health,
    responses={503: {"model": Health, "description": "Database unreachable"}},
)
def get_health(db: DbSession, response: Response) -> Health:
    checks: list[HealthCheck] = []
    head = _schema_head()
    current: str | None = None
    try:
        db.execute(text("SELECT 1"))
        checks.append(HealthCheck(name="database", ok=True))
    except SQLAlchemyError as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        checks.append(HealthCheck(name="database", ok=False, detail=type(exc).__name__))
        return Health(
            status="down",
            version=_app_version(),
            schema_revision=None,
            schema_head=head,
            checks=checks,
        )

    installed = dict(
        db.execute(text("SELECT extname, extversion FROM pg_extension")).tuples().all()
    )
    for ext in REQUIRED_EXTENSIONS:
        checks.append(
            HealthCheck(
                name=f"extension:{ext}",
                ok=ext in installed,
                detail=installed.get(ext, "not installed"),
            )
        )
    current = MigrationContext.configure(db.connection()).get_current_revision()
    checks.append(
        HealthCheck(
            name="schema",
            ok=current is not None and current == head,
            detail=f"{current or 'none'} (head {head})",
        )
    )
    db.rollback()
    overall = "ok" if all(c.ok for c in checks) else "degraded"
    return Health(
        status=overall,
        version=_app_version(),
        schema_revision=current,
        schema_head=head,
        checks=checks,
    )
