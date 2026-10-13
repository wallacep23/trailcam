"""The committed OpenAPI document (source of the TS client) matches the code (DESIGN §15)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trailcam.api.main import create_app
from trailcam.config import Settings

REPO = Path(__file__).resolve().parents[3]
COMMITTED = REPO / "apps" / "web" / "openapi.json"


def _spec() -> dict[str, Any]:
    return create_app(Settings(_env_file=None), configure_logs=False).openapi()


def test_expected_paths_exist() -> None:
    paths = set(_spec()["paths"])
    assert {
        "/api/v1/health",
        "/api/v1/jobs",
        "/api/v1/jobs/{job_id}",
        "/api/v1/jobs/{job_id}/retry",
        "/api/v1/properties",
    } <= paths


def test_operation_ids_are_unique_and_readable() -> None:
    ops = [op["operationId"] for item in _spec()["paths"].values() for op in item.values()]
    assert len(ops) == len(set(ops))
    assert "jobs_list_jobs" in ops
    assert "health_get_health" in ops


def test_committed_openapi_is_up_to_date() -> None:
    """Fails when the API changed but ``pnpm gen:api`` was not re-run."""
    assert COMMITTED.exists(), "run `pnpm --dir apps/web gen:api`"
    committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
    assert committed == _spec(), "apps/web/openapi.json is stale: run `pnpm --dir apps/web gen:api`"
