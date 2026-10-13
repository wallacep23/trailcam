"""Write the API's OpenAPI document to a file without starting a server or touching a database.

    uv run --project backend python scripts/export_openapi.py apps/web/openapi.json

The web app's ``pnpm gen:api`` runs this, then ``openapi-typescript`` to regenerate
``apps/web/src/api/schema.d.ts``. CI regenerates both and fails if they differ from the commit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from trailcam.api.main import create_app  # noqa: TID251 - the exporter must read the API
from trailcam.config import Settings


def export(target: Path) -> None:
    app = create_app(Settings(), configure_logs=False)
    spec = app.openapi()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    target = Path(args[0]) if args else Path("apps/web/openapi.json")
    export(target)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
