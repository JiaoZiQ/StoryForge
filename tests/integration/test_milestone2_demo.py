"""Ensure the documented Milestone 2 offline demonstration stays executable."""

import json
import subprocess
import sys
from pathlib import Path


def test_milestone2_demo_runs_without_credentials_or_network() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "scripts/milestone2_demo.py"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )

    payload = json.loads(result.stdout)
    assert payload == {
        "provider": "mock",
        "prompt": "demo.next-step",
        "prompt_version": "1.0.0",
        "output": {
            "summary": "Structured output validated locally.",
            "next_step": "Stop after Milestone 2 acceptance.",
        },
    }
