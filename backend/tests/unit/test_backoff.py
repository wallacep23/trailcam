"""Job retry backoff and progress maths."""

from __future__ import annotations

import pytest

from trailcam.core.backoff import progress_fraction, retry_delay_s


@pytest.mark.parametrize(
    ("attempt", "expected"), [(1, 5.0), (2, 10.0), (3, 20.0), (7, 320.0), (8, 600.0), (99, 600.0)]
)
def test_retry_delay_doubles_and_caps(attempt: int, expected: float) -> None:
    assert retry_delay_s(attempt, base_s=5, max_s=600) == expected


def test_retry_delay_zero_base_means_immediate() -> None:
    assert retry_delay_s(3, base_s=0, max_s=600) == 0.0


def test_retry_delay_rejects_attempt_zero() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        retry_delay_s(0, base_s=5, max_s=600)


@pytest.mark.parametrize(
    ("done", "total", "expected"),
    [(0, 10, 0.0), (5, 10, 0.5), (12, 10, 1.0), (-1, 10, 0.0), (3, None, None), (3, 0, None)],
)
def test_progress_fraction(done: int, total: int | None, expected: float | None) -> None:
    assert progress_fraction(done, total) == expected
