"""Seed a development database with a starting property. Idempotent (matched by name).

    uv run --project backend python scripts/dev_seed.py            # local
    docker compose exec api python /app/scripts/dev_seed.py        # in Docker

Creates one property from ``TRAILCAM_PROPERTY_DEFAULTS__*`` settings (name, timezone, centroid).
It deliberately creates **no sites**: sites, their names and aliases are always the user's own,
created on the Setup screen (FR-SITE-2, M1). Pass ``--selftest`` to also queue a demo job.
"""

from __future__ import annotations

import argparse
import sys

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session

from trailcam.config import get_settings
from trailcam.db.models import Property
from trailcam.db.session import session_scope
from trailcam.pipeline import jobs


def seed(session: Session, *, with_selftest: bool = False) -> dict[str, int]:
    defaults = get_settings().property_defaults
    created = {"property": 0, "job": 0}

    prop = session.scalars(select(Property).where(Property.name == defaults.name)).first()
    if prop is None:
        session.add(
            Property(
                name=defaults.name,
                tz=defaults.timezone,
                centroid=WKTElement(
                    f"POINT({defaults.centroid_lon} {defaults.centroid_lat})", srid=4326
                ),
            )
        )
        session.flush()
        created["property"] += 1

    if with_selftest:
        result = jobs.enqueue(
            session,
            "system.selftest",
            {"steps": 10, "sleep_s": 0.3, "fail_times": 1},
            dedupe_key="dev_seed:selftest",
        )
        created["job"] += int(result.created)
    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true", help="also queue a demo job")
    args = parser.parse_args(argv)
    with session_scope() as session:
        created = seed(session, with_selftest=args.selftest)
    print(f"dev_seed: created {created}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
