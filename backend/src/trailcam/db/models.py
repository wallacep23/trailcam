"""ORM models for every table in DESIGN §8.

Conventions (ADR 0002):

* ids are UUIDv7, timestamps are ``timestamptz`` in UTC;
* enumerations are ``text`` + ``CHECK`` built from :mod:`trailcam.core.types`;
* every derived row carries ``produced_by`` (stage, model, version, config hash);
* geography columns use SRID 4326; embeddings use an un-dimensioned ``vector`` plus ``dim``.

The Alembic migration ``0001_initial_schema`` must stay in sync with this module; the integration
test ``test_migration_matches_models`` fails if they drift.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geography
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Double,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trailcam.core.types import (
    Confidence,
    DeerClass,
    DetectionClass,
    GoldenSplit,
    JobStatus,
    LabelTargetType,
    LabelTrust,
    MediaKind,
    MediaStatus,
    RutPhase,
    TimeSource,
)
from trailcam.db.base import (
    Base,
    created_at,
    enum_check,
    produced_by,
    updated_at,
    uuid_pk,
)

POINT = Geography(geometry_type="POINT", srid=4326, spatial_index=False)
POLYGON = Geography(geometry_type="POLYGON", srid=4326, spatial_index=False)


# --------------------------------------------------------------------------- property & sites
class Property(Base):
    __tablename__ = "property"
    __table_args__ = (
        UniqueConstraint("name"),
        Index("ix_property_boundary", "boundary", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    tz: Mapped[str] = mapped_column(Text, nullable=False)
    boundary: Mapped[Any | None] = mapped_column(POLYGON, nullable=True)
    # Used for weather/sun/moon until a boundary is drawn (DESIGN §13.1).
    centroid: Mapped[Any | None] = mapped_column(POINT, nullable=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    sites: Mapped[list[Site]] = relationship(back_populates="property")


class Site(Base):
    __tablename__ = "site"
    __table_args__ = (
        UniqueConstraint("property_id", "name"),
        Index("ix_site_location", "location", postgresql_using="gist"),
        Index("ix_site_aliases", "aliases", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("property.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    location: Mapped[Any | None] = mapped_column(POINT, nullable=True)
    scene_fingerprint: Mapped[Any | None] = mapped_column(Vector(), nullable=True)
    last_heading_deg: Mapped[float | None] = mapped_column(Double, nullable=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    property: Mapped[Property] = relationship(back_populates="sites")


class Camera(Base):
    __tablename__ = "camera"

    id: Mapped[uuid.UUID] = uuid_pk()
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("property.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nickname: Mapped[str | None] = mapped_column(Text)
    make: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    serial: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


class Deployment(Base):
    """One camera at one site with one heading for a time window. One folder = one deployment."""

    __tablename__ = "deployment"
    __table_args__ = (
        CheckConstraint(
            "heading_deg IS NULL OR (heading_deg >= 0 AND heading_deg < 360)", name="heading_range"
        ),
        CheckConstraint("fov_deg > 0 AND fov_deg <= 180", name="fov_range"),
        CheckConstraint("end_at IS NULL OR start_at IS NULL OR end_at >= start_at", name="window"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("site.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    camera_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("camera.id", ondelete="SET NULL"), nullable=True, index=True
    )
    heading_deg: Mapped[float | None] = mapped_column(Double)
    fov_deg: Mapped[float] = mapped_column(Double, nullable=False, server_default=text("55"))
    start_at: Mapped[datetime | None] = mapped_column()
    end_at: Mapped[datetime | None] = mapped_column()
    clock_offset_s: Mapped[float] = mapped_column(Double, nullable=False, server_default=text("0"))
    source_folder: Mapped[str] = mapped_column(Text, nullable=False)
    frame_calibration: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


# --------------------------------------------------------------------------- media & frames
class Media(Base):
    """One immutable source file, identified by content hash (FR-ING-4, FR-ING-5)."""

    __tablename__ = "media"
    __table_args__ = (
        UniqueConstraint("sha256"),
        UniqueConstraint("deployment_id", "path"),
        enum_check("kind", MediaKind),
        enum_check("status", MediaStatus),
        enum_check("time_source", TimeSource),
        enum_check("time_confidence", Confidence),
        Index("ix_media_deployment_id_captured_at", "deployment_id", "captured_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployment.id", ondelete="CASCADE"), nullable=False
    )
    sha256: Mapped[str | None] = mapped_column(Text)  # filled by the hash stage
    path: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    duration_s: Mapped[float | None] = mapped_column(Double)
    fps: Mapped[float | None] = mapped_column(Double)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    captured_at: Mapped[datetime | None] = mapped_column()
    time_source: Mapped[str | None] = mapped_column(Text)
    time_confidence: Mapped[str | None] = mapped_column(Text)
    raw_time_candidates: Mapped[list[Any] | None] = mapped_column(JSONB)
    seq_no: Mapped[int | None] = mapped_column(Integer)
    burst_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(f"'{MediaStatus.DISCOVERED.value}'")
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class MediaQuality(Base):
    __tablename__ = "media_quality"

    media_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    blur: Mapped[float | None] = mapped_column(Double)
    fog: Mapped[float | None] = mapped_column(Double)
    darkness: Mapped[float | None] = mapped_column(Double)
    is_ir_night: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[float | None] = mapped_column(Double)
    produced_by: Mapped[dict[str, Any]] = produced_by()


class FrameSample(Base):
    __tablename__ = "frame_sample"
    __table_args__ = (UniqueConstraint("media_id", "frame_idx"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    media_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )
    t_offset_s: Mapped[float] = mapped_column(Double, nullable=False)
    frame_idx: Mapped[int] = mapped_column(Integer, nullable=False)


class Detection(Base):
    __tablename__ = "detection"
    __table_args__ = (
        enum_check("class", DetectionClass),
        CheckConstraint("conf >= 0 AND conf <= 1", name="conf_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    frame_sample_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frame_sample.id", ondelete="CASCADE"), nullable=False, index=True
    )
    class_: Mapped[str] = mapped_column("class", Text, nullable=False)
    conf: Mapped[float] = mapped_column(Double, nullable=False)
    # Normalized [0, 1] box: top-left x/y, width, height.
    bbox_x: Mapped[float] = mapped_column(Double, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Double, nullable=False)
    bbox_w: Mapped[float] = mapped_column(Double, nullable=False)
    bbox_h: Mapped[float] = mapped_column(Double, nullable=False)
    produced_by: Mapped[dict[str, Any]] = produced_by()


class Track(Base):
    __tablename__ = "track"

    id: Mapped[uuid.UUID] = uuid_pk()
    media_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"), nullable=False, index=True
    )
    det_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default=text("'{}'::uuid[]")
    )
    first_t: Mapped[float | None] = mapped_column(Double)
    last_t: Mapped[float | None] = mapped_column(Double)
    entry_xy: Mapped[list[float] | None] = mapped_column(ARRAY(Double))
    exit_xy: Mapped[list[float] | None] = mapped_column(ARRAY(Double))
    screen_motion: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    mean_box_area: Mapped[float | None] = mapped_column(Double)
    quality: Mapped[float | None] = mapped_column(Double)
    produced_by: Mapped[dict[str, Any]] = produced_by()


class Individual(Base):
    """A named or auto-clustered specific buck."""

    __tablename__ = "individual"

    id: Mapped[uuid.UUID] = uuid_pk()
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("property.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(Text)
    starred: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    first_seen: Mapped[datetime | None] = mapped_column()
    last_seen: Mapped[datetime | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(Text)
    cover_crop_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


class Observation(Base):
    """A track enriched with class, direction and optional individual; what analytics read."""

    __tablename__ = "observation"
    __table_args__ = (enum_check("deer_class", DeerClass),)

    id: Mapped[uuid.UUID] = uuid_pk()
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("track.id", ondelete="CASCADE"), nullable=False, index=True
    )
    species: Mapped[str | None] = mapped_column(Text)
    deer_class: Mapped[str | None] = mapped_column(Text)
    class_probs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    entry_bearing_deg: Mapped[float | None] = mapped_column(Double)
    exit_bearing_deg: Mapped[float | None] = mapped_column(Double)
    notable_score: Mapped[float | None] = mapped_column(Double)
    individual_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("individual.id", ondelete="SET NULL"), index=True
    )
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    produced_by: Mapped[dict[str, Any]] = produced_by()


class Embedding(Base):
    """Track embedding. Dimension varies by model, so the column is an un-dimensioned ``vector``
    and per-model HNSW indexes are created when a model is registered (ADR 0002)."""

    __tablename__ = "embedding"
    __table_args__ = (Index("ix_embedding_model", "model"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("track.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    dim: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    vector: Mapped[Any] = mapped_column(Vector(), nullable=False)
    crop_ref: Mapped[str | None] = mapped_column(Text)
    produced_by: Mapped[dict[str, Any]] = produced_by()


# --------------------------------------------------------------------------- events & conditions
class Event(Base):
    """Independent visit at one deployment; the unit of analysis (DESIGN §3, §13.2)."""

    __tablename__ = "event"
    __table_args__ = (Index("ix_event_deployment_id_start_at", "deployment_id", "start_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployment.id", ondelete="CASCADE"), nullable=False
    )
    start_at: Mapped[datetime] = mapped_column(nullable=False)
    end_at: Mapped[datetime] = mapped_column(nullable=False)
    n_deer: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    n_bucks: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    n_does: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    n_fawns: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    species_set: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    dominant_direction: Mapped[float | None] = mapped_column(Double)
    has_notable_buck: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    individual_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default=text("'{}'::uuid[]")
    )
    produced_by: Mapped[dict[str, Any]] = produced_by()


class ConditionsHourly(Base):
    """Cached hourly weather per property (FR-CON-1)."""

    __tablename__ = "conditions_hourly"

    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("property.id", ondelete="CASCADE"), primary_key=True
    )
    hour_utc: Mapped[datetime] = mapped_column(primary_key=True)
    temp_c: Mapped[float | None] = mapped_column(Double)
    wind_ms: Mapped[float | None] = mapped_column(Double)
    wind_dir_deg: Mapped[float | None] = mapped_column(Double)
    gust_ms: Mapped[float | None] = mapped_column(Double)
    pressure_hpa: Mapped[float | None] = mapped_column(Double)
    precip_mm: Mapped[float | None] = mapped_column(Double)
    cloud_pct: Mapped[float | None] = mapped_column(Double)
    humidity: Mapped[float | None] = mapped_column(Double)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = created_at()


class EventConditions(Base):
    """Denormalized conditions at an event's time, for fast filtering (FR-CON-1..3)."""

    __tablename__ = "event_conditions"
    __table_args__ = (enum_check("rut_phase", RutPhase),)

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("event.id", ondelete="CASCADE"), primary_key=True
    )
    temp_c: Mapped[float | None] = mapped_column(Double)
    wind_ms: Mapped[float | None] = mapped_column(Double)
    wind_dir_deg: Mapped[float | None] = mapped_column(Double)
    gust_ms: Mapped[float | None] = mapped_column(Double)
    pressure_hpa: Mapped[float | None] = mapped_column(Double)
    precip_mm: Mapped[float | None] = mapped_column(Double)
    cloud_pct: Mapped[float | None] = mapped_column(Double)
    humidity: Mapped[float | None] = mapped_column(Double)
    pressure_trend_3h: Mapped[float | None] = mapped_column(Double)
    temp_delta_24h: Mapped[float | None] = mapped_column(Double)
    mins_from_sunrise: Mapped[float | None] = mapped_column(Double)
    mins_from_sunset: Mapped[float | None] = mapped_column(Double)
    sun_alt: Mapped[float | None] = mapped_column(Double)
    moon_phase: Mapped[float | None] = mapped_column(Double)
    moon_illum: Mapped[float | None] = mapped_column(Double)
    moon_alt: Mapped[float | None] = mapped_column(Double)
    day_of_year: Mapped[int | None] = mapped_column(SmallInteger)
    rut_phase: Mapped[str | None] = mapped_column(Text)
    produced_by: Mapped[dict[str, Any]] = produced_by()


class Effort(Base):
    """Hourly camera activity; the denominator of every rate (DESIGN §9.4, FR-ANA-1)."""

    __tablename__ = "effort"

    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployment.id", ondelete="CASCADE"), primary_key=True
    )
    hour_utc: Mapped[datetime] = mapped_column(primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)


# --------------------------------------------------------------------------- labels & evaluation
class Label(Base):
    """Append-only fact about a target. Latest human label wins; models never overwrite humans."""

    __tablename__ = "label"
    __table_args__ = (
        enum_check("target_type", LabelTargetType),
        enum_check("trust", LabelTrust),
        Index("ix_label_target", "target_type", "target_id", "field", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    trust: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("label.id", ondelete="SET NULL")
    )


class GoldenSplitRow(Base):
    """Frozen evaluation split assignment, by deployment (DESIGN §16.1)."""

    __tablename__ = "golden_split"
    __table_args__ = (enum_check("split", GoldenSplit),)

    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    split: Mapped[str] = mapped_column(Text, nullable=False)
    split_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at()


class ModelVersion(Base):
    """Mirror of ``models/registry.yaml`` with evaluation metrics (NFR-6, NFR-7)."""

    __tablename__ = "model_version"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, primary_key=True)
    sha256: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at()


# --------------------------------------------------------------------------- jobs & hunting log
class Job(Base):
    """Postgres-backed job queue row (ADR 0003)."""

    __tablename__ = "job"
    __table_args__ = (
        enum_check("status", JobStatus),
        CheckConstraint("attempts >= 0", name="attempts_nonneg"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_pos"),
        # Claim path: queued jobs ordered by priority then age.
        Index(
            "ix_job_claim",
            "priority",
            "run_after",
            postgresql_where=text("status = 'queued'"),
        ),
        Index("ix_job_status_created_at", "status", "created_at"),
        # At most one live job per idempotency key (target, stage, model_version, config_hash).
        Index(
            "uq_job_dedupe_key_active",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running') AND dedupe_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(f"'{JobStatus.QUEUED.value}'")
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    dedupe_key: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    run_after: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    locked_by: Mapped[str | None] = mapped_column(Text)
    heartbeat_at: Mapped[datetime | None] = mapped_column()
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class HuntLog(Base):
    """User-logged hunt sits: human pressure and forecast validation (FR-CON-4)."""

    __tablename__ = "hunt_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("site.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_at: Mapped[datetime] = mapped_column(nullable=False)
    end_at: Mapped[datetime | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


ALL_TABLES: tuple[str, ...] = (
    "property",
    "site",
    "camera",
    "deployment",
    "media",
    "media_quality",
    "frame_sample",
    "detection",
    "track",
    "observation",
    "embedding",
    "individual",
    "event",
    "conditions_hourly",
    "event_conditions",
    "effort",
    "label",
    "golden_split",
    "model_version",
    "job",
    "hunt_log",
)
"""Every table from DESIGN §8 (21). Tests assert the migration creates exactly these."""
