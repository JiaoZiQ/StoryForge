"""Milestone 9 product-demo command."""

from __future__ import annotations

import argparse
from typing import Any

from storyforge.m9_demo import run_demo_m9


def _demo_m9(args: argparse.Namespace) -> dict[str, object]:
    return run_demo_m9(frontend_base_url=args.frontend_url).model_dump(mode="json")


def configure_m9_commands(commands: Any) -> None:
    """Register the M9 data-preparation command."""
    demo = commands.add_parser("demo-m9", help="Prepare a PostgreSQL Web UI demonstration")
    demo.add_argument("--frontend-url", default="http://localhost:3000")
    demo.add_argument("--output", choices=("human", "json"), default="human")
    demo.set_defaults(handler=_demo_m9)
