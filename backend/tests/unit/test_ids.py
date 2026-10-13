"""UUIDv7 ids (DESIGN §8)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from trailcam.core.ids import uuid7, uuid7_from_parts, uuid7_time


def test_uuid7_has_version_7_and_rfc_variant() -> None:
    value = uuid7()
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_uuid7_is_strictly_increasing_within_a_process() -> None:
    ids = [uuid7() for _ in range(20_000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_uuid7_embeds_creation_time() -> None:
    before = datetime.now(UTC) - timedelta(milliseconds=5)
    created = uuid7_time(uuid7())
    assert before <= created <= datetime.now(UTC) + timedelta(milliseconds=5)


def test_uuid7_from_parts_layout() -> None:
    value = uuid7_from_parts(0x0123456789AB, 0xABC, 0x3FFFFFFFFFFFFFFF)
    assert str(value).startswith("01234567-89ab-7abc-bfff")
    assert value.version == 7


def test_uuid7_from_parts_rejects_out_of_range_time() -> None:
    with pytest.raises(ValueError, match="out of range"):
        uuid7_from_parts(1 << 48, 0, 0)


def test_uuid7_time_rejects_other_versions() -> None:
    with pytest.raises(ValueError, match="not a UUIDv7"):
        uuid7_time(uuid.uuid4())
