"""UUIDv7 identifiers (DESIGN §8: all ids are UUIDv7).

UUIDv7 is time-ordered, so primary-key indexes stay compact and ids sort by creation time.
Python 3.14 adds ``uuid.uuid7``; until the project moves to 3.14 we generate them here.
Layout (RFC 9562 §5.7): 48-bit Unix ms timestamp | 4-bit version | 12-bit rand_a |
2-bit variant | 62-bit rand_b. ``rand_a`` holds a per-millisecond counter so ids created in the
same millisecond by one process are still strictly increasing (RFC 9562 §6.2, method 1).
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import UTC, datetime

_COUNTER_MAX = 0xFFF


class _Clock:
    """Process-wide (last millisecond, counter) state guarded by a lock."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.last_ms = 0
        self.counter = 0

    def tick(self) -> tuple[int, int]:
        with self.lock:
            now_ms = time.time_ns() // 1_000_000
            if now_ms > self.last_ms:
                self.last_ms = now_ms
                self.counter = int.from_bytes(os.urandom(2), "big") & 0x3FF  # leave headroom
            else:
                self.counter += 1
                if self.counter > _COUNTER_MAX:  # overflow: borrow the next millisecond
                    self.last_ms += 1
                    self.counter = 0
            return self.last_ms, self.counter


_clock = _Clock()


def uuid7_from_parts(unix_ms: int, rand_a: int, rand_b: int) -> uuid.UUID:
    """Assemble a UUIDv7 from its fields. Pure; used by :func:`uuid7` and by tests."""
    if not 0 <= unix_ms < 1 << 48:
        raise ValueError("unix_ms out of range for UUIDv7")
    value = (unix_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= (rand_a & 0xFFF) << 64
    value |= 0b10 << 62
    value |= rand_b & ((1 << 62) - 1)
    return uuid.UUID(int=value)


def uuid7() -> uuid.UUID:
    """Return a new, monotonically increasing (per process) UUIDv7."""
    ms, counter = _clock.tick()
    rand_b = int.from_bytes(os.urandom(8), "big")
    return uuid7_from_parts(ms, counter, rand_b)


def uuid7_time(value: uuid.UUID) -> datetime:
    """Return the creation time embedded in a UUIDv7."""
    if value.version != 7:
        raise ValueError("not a UUIDv7")
    return datetime.fromtimestamp((value.int >> 80) / 1000, tz=UTC)
