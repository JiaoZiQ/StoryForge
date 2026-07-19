"""Whole-book CLI transport behavior."""

from __future__ import annotations

import argparse
import urllib.error

import pytest

from storyforge.cli.m12 import _watch_sse


class _Stream:
    def __enter__(self) -> _Stream:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(
            [
                b"id: 1\n",
                b'data: {"status":"running","progress":50,"step":"global_review"}\n',
                b'data: {"status":"succeeded","progress":100,"step":"completed"}\n',
            ]
        )


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        api_url="http://127.0.0.1:8000",
        book_run_id=12,
        sse_timeout=0.1,
        output="json",
    )


def test_book_watch_uses_sse_until_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Stream())
    assert _watch_sse(_args()) is True


def test_book_watch_falls_back_when_sse_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    assert _watch_sse(_args()) is False
