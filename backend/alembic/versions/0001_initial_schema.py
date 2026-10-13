"""Initial schema: every table in DESIGN §8 (M0).

Creates the ``postgis`` and ``vector`` extensions, then the 21 tables. Generated with
``alembic revision --autogenerate`` from ``trailcam.db.models`` and reviewed by hand; the
integration test ``test_migration_matches_models`` keeps the two in sync.

Revision ID: 0001
Revises:
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import geoalchemy2
import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "golden_split",
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("split", sa.Text(), nullable=False),
        sa.Column("split_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "split IN ('train', 'val', 'test')", name=op.f("ck_golden_split_split_valid")
        ),
        sa.PrimaryKeyConstraint("target_id", name=op.f("pk_golden_split")),
    )
    op.create_table(
        "job",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("progress", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "run_after", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("locked_by", sa.Text(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name=op.f("ck_job_status_valid"),
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_job_attempts_nonneg")),
        sa.CheckConstraint("max_attempts >= 1", name=op.f("ck_job_max_attempts_pos")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job")),
    )
    op.create_index(
        "ix_job_claim",
        "job",
        ["priority", "run_after"],
        unique=False,
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index("ix_job_status_created_at", "job", ["status", "created_at"], unique=False)
    op.create_index(op.f("ix_job_type"), "job", ["type"], unique=False)
    op.create_index(
        "uq_job_dedupe_key_active",
        "job",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running') AND dedupe_key IS NOT NULL"),
    )
    op.create_table(
        "label",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("trust", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("supersedes_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "target_type IN ('media', 'track', 'observation', 'individual')",
            name=op.f("ck_label_target_type_valid"),
        ),
        sa.CheckConstraint(
            "trust IN ('ground_truth', 'human', 'model')", name=op.f("ck_label_trust_valid")
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["label.id"],
            name=op.f("fk_label_supersedes_id_label"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_label")),
    )
    op.create_index(
        "ix_label_target",
        "label",
        ["target_type", "target_id", "field", "created_at"],
        unique=False,
    )
    op.create_table(
        "model_version",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("license", sa.Text(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("name", "version", name=op.f("pk_model_version")),
    )
    op.create_table(
        "property",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("tz", sa.Text(), nullable=False),
        sa.Column(
            "boundary",
            geoalchemy2.types.Geography(
                geometry_type="POLYGON",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeogFromText",
                name="geography",
            ),
            nullable=True,
        ),
        sa.Column(
            "centroid",
            geoalchemy2.types.Geography(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeogFromText",
                name="geography",
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property")),
        sa.UniqueConstraint("name", name=op.f("uq_property_name")),
    )
    op.create_index(
        "ix_property_boundary", "property", ["boundary"], unique=False, postgresql_using="gist"
    )
    op.create_table(
        "camera",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("nickname", sa.Text(), nullable=True),
        sa.Column("make", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("serial", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_camera_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_camera")),
    )
    op.create_index(op.f("ix_camera_property_id"), "camera", ["property_id"], unique=False)
    op.create_table(
        "conditions_hourly",
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("hour_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("temp_c", sa.Double(), nullable=True),
        sa.Column("wind_ms", sa.Double(), nullable=True),
        sa.Column("wind_dir_deg", sa.Double(), nullable=True),
        sa.Column("gust_ms", sa.Double(), nullable=True),
        sa.Column("pressure_hpa", sa.Double(), nullable=True),
        sa.Column("precip_mm", sa.Double(), nullable=True),
        sa.Column("cloud_pct", sa.Double(), nullable=True),
        sa.Column("humidity", sa.Double(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_conditions_hourly_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("property_id", "hour_utc", name=op.f("pk_conditions_hourly")),
    )
    op.create_table(
        "individual",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("starred", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cover_crop_ref", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_individual_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_individual")),
    )
    op.create_index(op.f("ix_individual_property_id"), "individual", ["property_id"], unique=False)
    op.create_table(
        "site",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "location",
            geoalchemy2.types.Geography(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeogFromText",
                name="geography",
            ),
            nullable=True,
        ),
        sa.Column("scene_fingerprint", pgvector.sqlalchemy.vector.VECTOR(), nullable=True),
        sa.Column("last_heading_deg", sa.Double(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_site_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_site")),
        sa.UniqueConstraint("property_id", "name", name=op.f("uq_site_property_id_name")),
    )
    op.create_index("ix_site_aliases", "site", ["aliases"], unique=False, postgresql_using="gin")
    op.create_index("ix_site_location", "site", ["location"], unique=False, postgresql_using="gist")
    op.create_index(op.f("ix_site_property_id"), "site", ["property_id"], unique=False)
    op.create_table(
        "deployment",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("camera_id", sa.UUID(), nullable=True),
        sa.Column("heading_deg", sa.Double(), nullable=True),
        sa.Column("fov_deg", sa.Double(), server_default=sa.text("55"), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clock_offset_s", sa.Double(), server_default=sa.text("0"), nullable=False),
        sa.Column("source_folder", sa.Text(), nullable=False),
        sa.Column("frame_calibration", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "end_at IS NULL OR start_at IS NULL OR end_at >= start_at",
            name=op.f("ck_deployment_window"),
        ),
        sa.CheckConstraint("fov_deg > 0 AND fov_deg <= 180", name=op.f("ck_deployment_fov_range")),
        sa.CheckConstraint(
            "heading_deg IS NULL OR (heading_deg >= 0 AND heading_deg < 360)",
            name=op.f("ck_deployment_heading_range"),
        ),
        sa.ForeignKeyConstraint(
            ["camera_id"],
            ["camera.id"],
            name=op.f("fk_deployment_camera_id_camera"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["site_id"], ["site.id"], name=op.f("fk_deployment_site_id_site"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deployment")),
    )
    op.create_index(op.f("ix_deployment_camera_id"), "deployment", ["camera_id"], unique=False)
    op.create_index(op.f("ix_deployment_site_id"), "deployment", ["site_id"], unique=False)
    op.create_table(
        "hunt_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["site_id"], ["site.id"], name=op.f("fk_hunt_log_site_id_site"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hunt_log")),
    )
    op.create_index(op.f("ix_hunt_log_site_id"), "hunt_log", ["site_id"], unique=False)
    op.create_table(
        "effort",
        sa.Column("deployment_id", sa.UUID(), nullable=False),
        sa.Column("hour_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["deployment_id"],
            ["deployment.id"],
            name=op.f("fk_effort_deployment_id_deployment"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("deployment_id", "hour_utc", name=op.f("pk_effort")),
    )
    op.create_table(
        "event",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("deployment_id", sa.UUID(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("n_deer", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("n_bucks", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("n_does", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("n_fawns", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "species_set",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("dominant_direction", sa.Double(), nullable=True),
        sa.Column(
            "has_notable_buck", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "individual_ids",
            postgresql.ARRAY(sa.UUID()),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column("produced_by", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["deployment_id"],
            ["deployment.id"],
            name=op.f("fk_event_deployment_id_deployment"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event")),
    )
    op.create_index(
        "ix_event_deployment_id_start_at", "event", ["deployment_id", "start_at"], unique=False
    )
    op.create_table(
        "media",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("deployment_id", sa.UUID(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=True),
        sa.Column("duration_s", sa.Double(), nullable=True),
        sa.Column("fps", sa.Double(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_source", sa.Text(), nullable=True),
        sa.Column("time_confidence", sa.Text(), nullable=True),
        sa.Column("raw_time_candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("seq_no", sa.Integer(), nullable=True),
        sa.Column("burst_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'discovered'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('video', 'photo')", name=op.f("ck_media_kind_valid")),
        sa.CheckConstraint(
            "status IN ('discovered', 'hashed', 'probed', 'timed', 'sampled', 'empty', 'maybe_empty', 'animal', 'error')",
            name=op.f("ck_media_status_valid"),
        ),
        sa.CheckConstraint(
            "time_confidence IN ('high', 'medium', 'low')",
            name=op.f("ck_media_time_confidence_valid"),
        ),
        sa.CheckConstraint(
            "time_source IN ('ocr', 'container', 'filename', 'exif', 'mtime', 'manual')",
            name=op.f("ck_media_time_source_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["deployment_id"],
            ["deployment.id"],
            name=op.f("fk_media_deployment_id_deployment"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media")),
        sa.UniqueConstraint("deployment_id", "path", name=op.f("uq_media_deployment_id_path")),
        sa.UniqueConstraint("sha256", name=op.f("uq_media_sha256")),
    )
    op.create_index(op.f("ix_media_burst_id"), "media", ["burst_id"], unique=False)
    op.create_index(
        "ix_media_deployment_id_captured_at",
        "media",
        ["deployment_id", "captured_at"],
        unique=False,
    )
    op.create_table(
        "event_conditions",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("temp_c", sa.Double(), nullable=True),
        sa.Column("wind_ms", sa.Double(), nullable=True),
        sa.Column("wind_dir_deg", sa.Double(), nullable=True),
        sa.Column("gust_ms", sa.Double(), nullable=True),
        sa.Column("pressure_hpa", sa.Double(), nullable=True),
        sa.Column("precip_mm", sa.Double(), nullable=True),
        sa.Column("cloud_pct", sa.Double(), nullable=True),
        sa.Column("humidity", sa.Double(), nullable=True),
        sa.Column("pressure_trend_3h", sa.Double(), nullable=True),
        sa.Column("temp_delta_24h", sa.Double(), nullable=True),
        sa.Column("mins_from_sunrise", sa.Double(), nullable=True),
        sa.Column("mins_from_sunset", sa.Double(), nullable=True),
        sa.Column("sun_alt", sa.Double(), nullable=True),
        sa.Column("moon_phase", sa.Double(), nullable=True),
        sa.Column("moon_illum", sa.Double(), nullable=True),
        sa.Column("moon_alt", sa.Double(), nullable=True),
        sa.Column("day_of_year", sa.SmallInteger(), nullable=True),
        sa.Column("rut_phase", sa.Text(), nullable=True),
        sa.Column("produced_by", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "rut_phase IN ('pre_rut', 'seeking', 'chasing', 'breeding', 'post_rut', 'none')",
            name=op.f("ck_event_conditions_rut_phase_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["event.id"],
            name=op.f("fk_event_conditions_event_id_event"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_event_conditions")),
    )
    op.create_table(
        "frame_sample",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("media_id", sa.UUID(), nullable=False),
        sa.Column("t_offset_s", sa.Double(), nullable=False),
        sa.Column("frame_idx", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media.id"],
            name=op.f("fk_frame_sample_media_id_media"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_frame_sample")),
        sa.UniqueConstraint(
            "media_id", "frame_idx", name=op.f("uq_frame_sample_media_id_frame_idx")
        ),
    )
    op.create_table(
        "media_quality",
        sa.Column("media_id", sa.UUID(), nullable=False),
        sa.Column("blur", sa.Double(), nullable=True),
        sa.Column("fog", sa.Double(), nullable=True),
        sa.Column("darkness", sa.Double(), nullable=True),
        sa.Column("is_ir_night", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Double(), nullable=True),
        sa.Column("produced_by", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media.id"],
            name=op.f("fk_media_quality_media_id_media"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("media_id", name=op.f("pk_media_quality")),
    )
    op.create_table(
        "track",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("media_id", sa.UUID(), nullable=False),
        sa.Column(
            "det_ids",
            postgresql.ARRAY(sa.UUID()),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column("first_t", sa.Double(), nullable=True),
        sa.Column("last_t", sa.Double(), nullable=True),
        sa.Column("entry_xy", postgresql.ARRAY(sa.Double()), nullable=True),
        sa.Column("exit_xy", postgresql.ARRAY(sa.Double()), nullable=True),
        sa.Column("screen_motion", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("mean_box_area", sa.Double(), nullable=True),
        sa.Column("quality", sa.Double(), nullable=True),
        sa.Column("produced_by", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_id"], ["media.id"], name=op.f("fk_track_media_id_media"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_track")),
    )
    op.create_index(op.f("ix_track_media_id"), "track", ["media_id"], unique=False)
    op.create_table(
        "detection",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("frame_sample_id", sa.UUID(), nullable=False),
        sa.Column("class", sa.Text(), nullable=False),
        sa.Column("conf", sa.Double(), nullable=False),
        sa.Column("bbox_x", sa.Double(), nullable=False),
        sa.Column("bbox_y", sa.Double(), nullable=False),
        sa.Column("bbox_w", sa.Double(), nullable=False),
        sa.Column("bbox_h", sa.Double(), nullable=False),
        sa.Column("produced_by", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "class IN ('animal', 'person', 'vehicle')", name=op.f("ck_detection_class_valid")
        ),
        sa.CheckConstraint("conf >= 0 AND conf <= 1", name=op.f("ck_detection_conf_range")),
        sa.ForeignKeyConstraint(
            ["frame_sample_id"],
            ["frame_sample.id"],
            name=op.f("fk_detection_frame_sample_id_frame_sample"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detection")),
    )
    op.create_index(
        op.f("ix_detection_frame_sample_id"), "detection", ["frame_sample_id"], unique=False
    )
    op.create_table(
        "embedding",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("track_id", sa.UUID(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("dim", sa.SmallInteger(), nullable=False),
        sa.Column("vector", pgvector.sqlalchemy.vector.VECTOR(), nullable=False),
        sa.Column("crop_ref", sa.Text(), nullable=True),
        sa.Column("produced_by", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["track_id"], ["track.id"], name=op.f("fk_embedding_track_id_track"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_embedding")),
    )
    op.create_index("ix_embedding_model", "embedding", ["model"], unique=False)
    op.create_index(op.f("ix_embedding_track_id"), "embedding", ["track_id"], unique=False)
    op.create_table(
        "observation",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("track_id", sa.UUID(), nullable=False),
        sa.Column("species", sa.Text(), nullable=True),
        sa.Column("deer_class", sa.Text(), nullable=True),
        sa.Column("class_probs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("entry_bearing_deg", sa.Double(), nullable=True),
        sa.Column("exit_bearing_deg", sa.Double(), nullable=True),
        sa.Column("notable_score", sa.Double(), nullable=True),
        sa.Column("individual_id", sa.UUID(), nullable=True),
        sa.Column("accepted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("produced_by", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "deer_class IN ('buck', 'doe', 'fawn', 'antlerless', 'unknown')",
            name=op.f("ck_observation_deer_class_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["individual_id"],
            ["individual.id"],
            name=op.f("fk_observation_individual_id_individual"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["track_id"],
            ["track.id"],
            name=op.f("fk_observation_track_id_track"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_observation")),
    )
    op.create_index(
        op.f("ix_observation_individual_id"), "observation", ["individual_id"], unique=False
    )
    op.create_index(op.f("ix_observation_track_id"), "observation", ["track_id"], unique=False)


def downgrade() -> None:
    # Extensions are left installed: the database image may have created them, and other
    # databases objects (PostGIS's spatial_ref_sys) depend on them.
    op.drop_index(op.f("ix_observation_track_id"), table_name="observation")
    op.drop_index(op.f("ix_observation_individual_id"), table_name="observation")
    op.drop_table("observation")
    op.drop_index(op.f("ix_embedding_track_id"), table_name="embedding")
    op.drop_index("ix_embedding_model", table_name="embedding")
    op.drop_table("embedding")
    op.drop_index(op.f("ix_detection_frame_sample_id"), table_name="detection")
    op.drop_table("detection")
    op.drop_index(op.f("ix_track_media_id"), table_name="track")
    op.drop_table("track")
    op.drop_table("media_quality")
    op.drop_table("frame_sample")
    op.drop_table("event_conditions")
    op.drop_index("ix_media_deployment_id_captured_at", table_name="media")
    op.drop_index(op.f("ix_media_burst_id"), table_name="media")
    op.drop_table("media")
    op.drop_index("ix_event_deployment_id_start_at", table_name="event")
    op.drop_table("event")
    op.drop_table("effort")
    op.drop_index(op.f("ix_hunt_log_site_id"), table_name="hunt_log")
    op.drop_table("hunt_log")
    op.drop_index(op.f("ix_deployment_site_id"), table_name="deployment")
    op.drop_index(op.f("ix_deployment_camera_id"), table_name="deployment")
    op.drop_table("deployment")
    op.drop_index(op.f("ix_site_property_id"), table_name="site")
    op.drop_index("ix_site_location", table_name="site", postgresql_using="gist")
    op.drop_index("ix_site_aliases", table_name="site", postgresql_using="gin")
    op.drop_table("site")
    op.drop_index(op.f("ix_individual_property_id"), table_name="individual")
    op.drop_table("individual")
    op.drop_table("conditions_hourly")
    op.drop_index(op.f("ix_camera_property_id"), table_name="camera")
    op.drop_table("camera")
    op.drop_index("ix_property_boundary", table_name="property", postgresql_using="gist")
    op.drop_table("property")
    op.drop_table("model_version")
    op.drop_index("ix_label_target", table_name="label")
    op.drop_table("label")
    op.drop_index(
        "uq_job_dedupe_key_active",
        table_name="job",
        postgresql_where=sa.text("status IN ('queued', 'running') AND dedupe_key IS NOT NULL"),
    )
    op.drop_index(op.f("ix_job_type"), table_name="job")
    op.drop_index("ix_job_status_created_at", table_name="job")
    op.drop_index("ix_job_claim", table_name="job", postgresql_where=sa.text("status = 'queued'"))
    op.drop_table("job")
    op.drop_table("golden_split")
