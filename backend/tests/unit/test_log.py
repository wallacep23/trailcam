"""Structured logging (NFR-11)."""

from __future__ import annotations

import json
import logging
import sys

import pytest

from trailcam.log import ConsoleFormatter, JsonFormatter, bind_context, configure_logging


def _record(msg: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("trailcam.test", logging.INFO, __file__, 1, msg, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emits_one_object_with_context_and_extra() -> None:
    with bind_context(job_id="j-1", request_id="r-1"):
        line = JsonFormatter().format(_record(count=3))
    data = json.loads(line)
    assert data["msg"] == "hello"
    assert data["level"] == "info"
    assert data["logger"] == "trailcam.test"
    assert data["job_id"] == "j-1"
    assert data["request_id"] == "r-1"
    assert data["count"] == 3
    assert "\n" not in line


def test_context_is_restored_after_block() -> None:
    with bind_context(job_id="outer"):
        with bind_context(job_id="inner", stage="x"):
            pass
        data = json.loads(JsonFormatter().format(_record()))
    assert data["job_id"] == "outer"
    assert "stage" not in data
    assert "job_id" not in json.loads(JsonFormatter().format(_record()))


def test_json_formatter_includes_exceptions() -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = _record()
        record.exc_info = sys.exc_info()
    data = json.loads(JsonFormatter().format(record))
    assert "RuntimeError: boom" in data["exc"]


def test_console_formatter_shows_fields() -> None:
    line = ConsoleFormatter().format(_record(stage="scan"))
    assert "hello" in line
    assert "stage=scan" in line


def test_configure_logging_is_idempotent(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", "json")
    configure_logging("INFO", "json")
    ours = [h for h in logging.getLogger().handlers if getattr(h, "_trailcam", False)]
    assert len(ours) == 1
    logging.getLogger("trailcam.x").info("once", extra={"k": "v"})
    out = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert json.loads(out[-1])["k"] == "v"
