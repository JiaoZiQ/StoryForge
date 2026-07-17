"""Remove only disposable build and test artifacts inside this repository."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = (
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
    "htmlcov",
)
FILES = (".coverage", "coverage.xml")


def main() -> int:
    """Delete known generated paths without touching databases, env files, or Docker volumes."""
    for relative in DIRECTORIES:
        shutil.rmtree(ROOT / relative, ignore_errors=True)
    for relative in FILES:
        path = ROOT / relative
        if path.is_file():
            path.unlink()
    for path in ROOT.glob("*.egg-info"):
        if path.is_dir():
            shutil.rmtree(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
