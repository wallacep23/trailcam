"""Structured logging (NFR-11). Named ``log`` so it never shadows the stdlib ``logging``.

Every log line is one JSON object with ``ts``, ``level``, ``logger``, ``msg`` plus any context bound
with :func:`bind_context` (request id, job id, job type, worker id) and any ``extra={...}`` fields.
``log_format="console"`` gives a readable single-line format for local development.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

_CONTEXT: contextvars.ContextVar[Mapping[str, Any]] = contextvars.ContextVar(
    "trailcam_log_context", default=MappingProxyType({})
)

# Attributes every LogRecord has; anything else came from ``extra=`` and is emitted as a field.
_RESERVED = frozenset(
    vars(logging.LogRecord("x", logging.INFO, "x", 0, "x", None, None)).keys()
    | {"message", "asctime", "taskName"}
)


def current_context() -> dict[str, Any]:
    """Return a copy of the context bound to the current task/thread."""
    return dict(_CONTEXT.get())


@contextmanager
def bind_context(**fields: Any) -> Iterator[None]:
    """Attach ``fields`` to every log line emitted inside the ``with`` block."""
    token = _CONTEXT.set({**_CONTEXT.get(), **fields})
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def _record_fields(record: logging.LogRecord) -> dict[str, Any]:
    fields: dict[str, Any] = dict(_CONTEXT.get())
    for key, value in record.__dict__.items():
        if key not in _RESERVED and not key.startswith("_"):
            fields[key] = value
    return fields


class JsonFormatter(logging.Formatter):
    """Format records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(_record_fields(record))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Human-readable formatter that still shows the structured fields."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        fields = _record_fields(record)
        extra = " ".join(f"{k}={v}" for k, v in fields.items())
        line = f"{ts} {record.levelname:<7} {record.name}: {record.getMessage()}"
        if extra:
            line = f"{line}  [{extra}]"
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Install a single stdout handler on the root logger. Safe to call more than once."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else ConsoleFormatter())
    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "_trailcam", False):
            root.removeHandler(existing)
    handler._trailcam = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Route uvicorn's loggers through the same handler and format.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
