"""Guardrail: ``core/`` stays free of I/O, DB, GPU and framework imports (CLAUDE.md, §7)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[2] / "src" / "trailcam" / "core"

BANNED_MODULES = {
    "sqlalchemy", "alembic", "psycopg", "geoalchemy2", "pgvector", "fastapi", "starlette",
    "uvicorn", "pydantic_settings", "httpx", "requests", "urllib", "socket", "subprocess",
    "shutil", "glob", "torch", "onnxruntime", "cv2", "av", "PIL", "trailcam.db", "trailcam.api",
    "trailcam.pipeline", "trailcam.config", "trailcam.log", "trailcam.models",
    "trailcam.integrations", "trailcam.importers", "trailcam.learning",
}  # fmt: skip
BANNED_CALLS = {"open", "input", "print", "exec", "eval"}


def _core_files() -> list[Path]:
    return sorted(CORE.rglob("*.py"))


def test_core_package_exists() -> None:
    assert _core_files(), "core/ has no modules"


@pytest.mark.parametrize("path", _core_files(), ids=lambda p: p.name)
def test_core_module_is_pure(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            if any(name == b or name.startswith(b + ".") for b in BANNED_MODULES):
                problems.append(f"line {getattr(node, 'lineno', 0)}: imports {name}")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in BANNED_CALLS
        ):
            problems.append(f"line {getattr(node, 'lineno', 0)}: calls {node.func.id}()")
    assert not problems, f"{path.name} is not pure: {problems}"
