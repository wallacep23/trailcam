"""License gate (NFR-7): models must be MIT/Apache-2.0/BSD; no strong-copyleft Python deps.

    uv run --project backend python scripts/check_licenses.py [--registry models/registry.yaml]

1. Every entry in ``models/registry.yaml`` has the required fields and a permissive license.
2. Every installed Python distribution is scanned. AGPL/GPL (strong copyleft) or "non-commercial"
   licenses fail the check unless listed in ``ALLOWED_EXCEPTIONS`` with a reason. Unknown licenses
   are reported (and fail with ``--strict``).
"""

from __future__ import annotations

import argparse
import re
import sys
from importlib import metadata
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]

MODEL_LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"}
MODEL_FIELDS = ("name", "version", "file", "sha256", "license", "source")

# Weak-copyleft packages accepted after review (see docs/adr/0001-tech-stack.md).
ALLOWED_EXCEPTIONS: dict[str, str] = {
    "psycopg": "LGPL-3.0, used unmodified as an imported library; pg8000 (BSD) is the fallback",
    "psycopg-binary": "LGPL-3.0, binary wheel of psycopg (see psycopg)",
    "psycopg-c": "LGPL-3.0, C build of psycopg (see psycopg)",
}

_FORBIDDEN = re.compile(r"\b(A?GPL|GNU (Affero )?General Public|non[- ]?commercial|CC-BY-NC)", re.I)
_LGPL = re.compile(r"\b(LGPL|Lesser General Public)", re.I)


def check_registry(path: Path) -> list[str]:
    errors: list[str] = []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    models = data.get("models") or []
    if not isinstance(models, list):
        return [f"{path}: 'models' must be a list"]
    seen: set[tuple[str, str]] = set()
    for i, model in enumerate(models):
        where = f"{path.name}[{i}] {model.get('name', '?')}"
        missing = [f for f in MODEL_FIELDS if not model.get(f)]
        if missing:
            errors.append(f"{where}: missing {', '.join(missing)}")
        if model.get("license") not in MODEL_LICENSES:
            errors.append(
                f"{where}: license {model.get('license')!r} not in {sorted(MODEL_LICENSES)}"
            )
        sha = str(model.get("sha256", ""))
        if sha and not re.fullmatch(r"[0-9a-f]{64}", sha):
            errors.append(f"{where}: sha256 must be 64 lowercase hex characters")
        key = (str(model.get("name")), str(model.get("version")))
        if key in seen:
            errors.append(f"{where}: duplicate name+version")
        seen.add(key)
    return errors


def license_text(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    parts = [meta.get("License-Expression") or "", (meta.get("License") or "")[:200]]
    parts += [c for c in (meta.get_all("Classifier") or []) if c.startswith("License ::")]
    return " | ".join(p for p in parts if p).strip()


def check_python_deps(strict: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    unknown: list[str] = []
    for dist in sorted(metadata.distributions(), key=lambda d: (d.metadata["Name"] or "").lower()):
        name = (dist.metadata["Name"] or "").lower()
        text = license_text(dist)
        if name in ALLOWED_EXCEPTIONS:
            continue
        if not text:
            unknown.append(name)
        elif _FORBIDDEN.search(text) and not _LGPL.search(text):
            errors.append(f"python dependency {name}: {text}")
    if strict:
        errors += [f"python dependency {n}: license unknown" for n in unknown]
    return errors, unknown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", type=Path, default=REPO / "models" / "registry.yaml")
    parser.add_argument("--strict", action="store_true", help="fail on unknown licenses too")
    args = parser.parse_args(argv)

    errors = check_registry(args.registry)
    dep_errors, unknown = check_python_deps(args.strict)
    errors += dep_errors
    if unknown:
        print(f"note: no license metadata for: {', '.join(unknown)}")
    for err in errors:
        print(f"FAIL {err}")
    if errors:
        return 1
    print("OK  licenses OK (models registry + python dependencies)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
