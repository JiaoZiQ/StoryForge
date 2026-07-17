"""Export StoryForge's deterministic OpenAPI document for frontend type generation."""

from __future__ import annotations

import json
from pathlib import Path

from storyforge.api.app import create_app


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"
    document = create_app().openapi()
    target.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
