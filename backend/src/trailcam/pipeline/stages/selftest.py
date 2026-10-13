"""``system.selftest``: exercises the queue end to end (progress, retry, failure).

Payload (all optional):

* ``steps`` (int, default 5) and ``sleep_s`` (float, default 0.2): simulated work;
* ``fail_times`` (int, default 0): raise on the first N attempts, then succeed (retry demo);
* ``fatal`` (bool, default false): fail permanently without retrying.
"""

from __future__ import annotations

import time
from typing import Any

from trailcam.pipeline.jobs import FatalJobError
from trailcam.pipeline.registry import JobContext, job_handler

MAX_STEPS = 1000
MAX_SLEEP_S = 5.0


class SelfTestError(RuntimeError):
    """Deliberate failure used to demonstrate retries."""


@job_handler(
    "system.selftest",
    description="Simulated job that reports progress and can fail on purpose.",
    user_runnable=True,
)
def selftest(ctx: JobContext) -> dict[str, Any]:
    steps = max(1, min(int(ctx.payload.get("steps", 5)), MAX_STEPS))
    sleep_s = max(0.0, min(float(ctx.payload.get("sleep_s", 0.2)), MAX_SLEEP_S))
    fail_times = int(ctx.payload.get("fail_times", 0))
    if ctx.payload.get("fatal"):
        raise FatalJobError("selftest asked to fail permanently")
    for step in range(steps):
        time.sleep(sleep_s)
        ctx.progress(step + 1, steps, f"step {step + 1} of {steps}")
    if ctx.attempt <= fail_times:
        raise SelfTestError(f"selftest failing on purpose (attempt {ctx.attempt}/{fail_times})")
    return {"steps": steps, "attempt": ctx.attempt}
