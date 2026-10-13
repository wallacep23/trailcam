"""Application settings (NFR-5, NFR-11).

All settings come from environment variables prefixed ``TRAILCAM_`` (or a ``.env`` file), so the
same image runs in Docker, in CI and in a local ``uv`` dev setup. Nested values use ``__``
(for example ``TRAILCAM_WORKER__POLL_INTERVAL_S=0.5``).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LogFormat = Literal["json", "console"]
Environment = Literal["dev", "test", "prod"]


class WorkerSettings(BaseModel):
    """Job-queue worker behaviour."""

    poll_interval_s: float = Field(1.0, gt=0, description="Sleep between empty queue polls.")
    heartbeat_interval_s: float = Field(10.0, gt=0)
    stale_after_s: float = Field(
        300.0, gt=0, description="A running job with no heartbeat for this long is re-queued."
    )
    job_types: list[str] = Field(
        default_factory=list, description="Only claim these job types (empty = all registered)."
    )


class JobDefaults(BaseModel):
    """Defaults applied when a job is enqueued without explicit values."""

    max_attempts: int = Field(3, ge=1)
    backoff_base_s: float = Field(5.0, ge=0, description="First retry delay; doubles per attempt.")
    backoff_max_s: float = Field(600.0, ge=0)


class PropertyDefaults(BaseModel):
    """Defaults for the owner's first property (DESIGN §13.1, §18)."""

    name: str = "Judy's"
    timezone: str = "America/Detroit"
    centroid_lat: float = 42.493
    centroid_lon: float = -83.665


class Settings(BaseSettings):
    """Process-wide configuration. Construct via :func:`get_settings`."""

    model_config = SettingsConfigDict(
        env_prefix="TRAILCAM_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = "dev"
    database_url: str = "postgresql+psycopg://trailcam:trailcam@localhost:5432/trailcam"

    # Filesystem. Media roots are read-only to the app (FR-ING-5, NFR-4).
    media_roots: Annotated[list[Path], NoDecode] = Field(default_factory=list)
    cache_dir: Path = Path("./.trailcam-cache")
    backup_dir: Path = Path("./.trailcam-backups")
    models_registry: Path = Path("../models/registry.yaml")

    # Logging (NFR-11).
    log_level: str = "INFO"
    log_format: LogFormat = "json"

    # API.
    api_prefix: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    jobs: JobDefaults = Field(default_factory=JobDefaults)
    property_defaults: PropertyDefaults = Field(default_factory=PropertyDefaults)

    @field_validator("media_roots", "cors_origins", mode="before")
    @classmethod
    def _split_list(cls, value: object) -> object:
        """Accept a comma- or semicolon-separated string (friendlier for Windows paths)."""
        if isinstance(value, str):
            parts = [p.strip() for p in value.replace(";", ",").split(",")]
            return [p for p in parts if p]
        return value

    @field_validator("log_level")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
