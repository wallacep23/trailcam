"""Retry backoff for the job queue. Pure, so it is unit-tested without a database."""

from __future__ import annotations


def retry_delay_s(attempt: int, base_s: float, max_s: float) -> float:
    """Delay before retry number ``attempt`` (1 = first retry): ``base * 2**(attempt-1)``, capped.

    >>> retry_delay_s(1, 5, 600), retry_delay_s(3, 5, 600), retry_delay_s(20, 5, 600)
    (5.0, 20.0, 600.0)
    """
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    if base_s <= 0:
        return 0.0
    exponent = min(attempt - 1, 32)  # avoid huge floats; the cap applies long before this
    return float(min(base_s * (2**exponent), max_s))


def progress_fraction(done: int, total: int | None) -> float | None:
    """Return ``done/total`` clamped to [0, 1], or ``None`` when the total is unknown."""
    if total is None or total <= 0:
        return None
    return max(0.0, min(1.0, done / total))
