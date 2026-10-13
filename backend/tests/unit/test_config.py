"""Pydantic settings (TRAILCAM_* environment)."""

from __future__ import annotations

from pathlib import Path

import pytest

from trailcam.config import Settings


def test_defaults_target_the_owners_property() -> None:
    s = Settings(_env_file=None)
    assert s.property_defaults.timezone == "America/Detroit"
    assert (s.property_defaults.centroid_lat, s.property_defaults.centroid_lon) == (42.493, -83.665)
    assert s.api_prefix == "/api/v1"


def test_env_prefix_and_nested_delimiter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRAILCAM_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    monkeypatch.setenv("TRAILCAM_WORKER__POLL_INTERVAL_S", "0.25")
    monkeypatch.setenv("TRAILCAM_JOBS__MAX_ATTEMPTS", "7")
    monkeypatch.setenv("TRAILCAM_LOG_LEVEL", "debug")
    s = Settings(_env_file=None)
    assert s.database_url.endswith("@db:5432/x")
    assert s.worker.poll_interval_s == 0.25
    assert s.jobs.max_attempts == 7
    assert s.log_level == "DEBUG"


def test_media_roots_accept_windows_style_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TRAILCAM_MEDIA_ROOTS", r"C:\Users\pwall\Desktop\TrailCamera\Judy's; D:\Cards"
    )
    s = Settings(_env_file=None)
    assert s.media_roots == [Path(r"C:\Users\pwall\Desktop\TrailCamera\Judy's"), Path(r"D:\Cards")]


def test_cors_origins_from_comma_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRAILCAM_CORS_ORIGINS", "http://a:1,http://b:2")
    assert Settings(_env_file=None).cors_origins == ["http://a:1", "http://b:2"]


def test_invalid_values_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRAILCAM_JOBS__MAX_ATTEMPTS", "0")
    with pytest.raises(ValueError, match="max_attempts"):
        Settings(_env_file=None)
