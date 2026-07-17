"""Milestone 7 PostgreSQL deployment demonstration command."""

from __future__ import annotations

import argparse
from typing import Any

from storyforge.m7_demo import run_demo_m7


def _demo_m7(_: argparse.Namespace) -> dict[str, object]:
    return run_demo_m7().model_dump(mode="json")


def configure_m7_commands(commands: Any) -> None:
    """Register the explicit PostgreSQL demo command."""
    demo = commands.add_parser("demo-m7", help="Run the PostgreSQL-backed M7 demonstration")
    demo.add_argument("--output", choices=("human", "json"), default="human")
    demo.set_defaults(handler=_demo_m7)
