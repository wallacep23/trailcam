"""Job handler registry."""

from __future__ import annotations

import pytest

from trailcam.pipeline import registry
from trailcam.pipeline.registry import JobContext, job_handler, load_handlers


def test_selftest_is_registered_and_user_runnable() -> None:
    handlers = load_handlers()
    assert "system.selftest" in handlers
    assert handlers["system.selftest"].user_runnable


def test_duplicate_registration_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "HANDLERS", {})

    @job_handler("x.one")
    def first(ctx: JobContext) -> None:
        """First."""

    assert registry.HANDLERS["x.one"].description == "First."
    assert not registry.HANDLERS["x.one"].user_runnable

    with pytest.raises(ValueError, match="duplicate"):

        @job_handler("x.one")
        def second(ctx: JobContext) -> None: ...
