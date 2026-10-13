"""Pydantic DTOs: the source of the OpenAPI document and therefore of the TS client (DESIGN §15)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator

from trailcam.core.types import JobStatus


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- health
class HealthCheck(ApiModel):
    name: str
    ok: bool
    detail: str | None = None


class Health(ApiModel):
    status: Literal["ok", "degraded", "down"]
    version: str
    schema_revision: str | None
    schema_head: str | None
    checks: list[HealthCheck]


# --------------------------------------------------------------------------- jobs
class JobProgress(ApiModel):
    done: int
    total: int | None = None
    fraction: float | None = None
    message: str | None = None


class JobOut(ApiModel):
    id: uuid.UUID
    type: str
    status: JobStatus
    payload: dict[str, Any]
    priority: int
    attempts: int
    max_attempts: int
    dedupe_key: str | None
    error: str | None
    progress: JobProgress | None
    result: dict[str, Any] | None
    run_after: datetime
    locked_by: str | None
    heartbeat_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JobPage(ApiModel):
    items: list[JobOut]
    total: int
    limit: int
    offset: int


class JobCreate(ApiModel):
    type: str = Field(description="A user-runnable job type (see GET /jobs/types).")
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    max_attempts: int | None = Field(default=None, ge=1, le=20)


class JobTypeOut(ApiModel):
    type: str
    description: str
    user_runnable: bool


class JobStats(ApiModel):
    counts: dict[JobStatus, int]


# --------------------------------------------------------------------------- properties
class LatLon(ApiModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class PropertyCreate(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    tz: str = Field(description="IANA timezone, e.g. America/Detroit.")
    centroid: LatLon | None = None

    @field_validator("tz")
    @classmethod
    def _valid_tz(cls, value: str) -> str:
        if value not in available_timezones():
            raise ValueError(f"unknown IANA timezone: {value}")
        return value


class PropertyOut(ApiModel):
    id: uuid.UUID
    name: str
    tz: str
    centroid: LatLon | None
    has_boundary: bool
    site_count: int
    created_at: datetime


class ErrorOut(ApiModel):
    detail: str
