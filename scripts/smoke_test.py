"""End-to-end smoke test of a running stack (M0 acceptance). Standard library only.

    python scripts/smoke_test.py [--base http://localhost:5173] [--timeout 120]

1. waits for ``/api/v1/health`` to report ``ok`` (DB up, PostGIS + pgvector, schema at head);
2. queues a ``system.selftest`` job that fails its first attempt;
3. waits for the worker to retry it to ``succeeded`` with progress 100%.

Point ``--base`` at the web UI (default, checks the nginx /api proxy too) or at the API (:8000).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def call(base: str, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(  # noqa: S310 - local URL supplied by the operator
        base.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as res:  # noqa: S310
        return json.loads(res.read())


def wait_for(what: str, timeout: float, probe: Any) -> Any:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        try:
            last = probe()
            if last:
                return last
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            last = exc
        time.sleep(1)
    raise SystemExit(f"FAIL timed out waiting for {what} (last: {last})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://localhost:5173")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    base = args.base

    def healthy() -> Any:
        h = call(base, "GET", "/api/v1/health")
        return h if h["status"] == "ok" else None

    health = wait_for("healthy API", args.timeout, healthy)
    print(
        f"OK  health ok: schema {health['schema_revision']}, checks "
        f"{', '.join(c['name'] for c in health['checks'])}"
    )

    job = call(
        base,
        "POST",
        "/api/v1/jobs",
        {
            "type": "system.selftest",
            "payload": {"steps": 4, "sleep_s": 0.25, "fail_times": 1},
            "max_attempts": 3,
        },
    )
    print(f"OK  queued self-test job {job['id']}")

    def finished() -> Any:
        j = call(base, "GET", f"/api/v1/jobs/{job['id']}")
        return j if j["status"] in ("succeeded", "failed") else None

    # First attempt fails on purpose; the retry waits for the configured backoff (default 5 s).
    done = wait_for("self-test job to finish", args.timeout, finished)
    ok = (
        done["status"] == "succeeded"
        and done["attempts"] == 2
        and (done.get("progress") or {}).get("fraction") == 1.0
    )
    if not ok:
        print(f"FAIL unexpected job state: {json.dumps(done, indent=2)}")
        return 1
    print(f"OK  worker ran the job: failed once, retried, succeeded (attempts={done['attempts']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
