"""Portable database-wait command for local diagnostics and containers."""

from storyforge.runtime import wait_for_db_main

if __name__ == "__main__":
    raise SystemExit(wait_for_db_main())
