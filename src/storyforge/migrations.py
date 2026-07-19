"""Migration revision constants shared by readiness and deployment tooling."""

from pathlib import Path

MIGRATION_HEAD = "b61d3f7a2c10"


def alembic_config_path() -> Path:
    """Locate the checked-in Alembic config in source and installed container layouts."""
    candidates = (
        Path.cwd() / "alembic.ini",
        Path(__file__).resolve().parents[2] / "alembic.ini",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("alembic.ini was not found in the application working directory")
