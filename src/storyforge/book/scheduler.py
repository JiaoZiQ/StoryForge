"""Dependency-aware chapter scheduling decisions without executing workflow code."""

from __future__ import annotations

from collections import deque

from storyforge.book.models import ChapterScheduleDecision
from storyforge.enums import BookRunMode
from storyforge.exceptions import DomainValidationError


class BookChapterScheduler:
    """Choose one bounded, dependency-safe chapter action at a time."""

    _DONE = frozenset({"accepted", "completed"})
    _ACTIVE = frozenset({"pending", "queued", "leased", "running", "retry_scheduled"})

    def __init__(self, *, concurrency: int = 1, maximum_concurrency: int = 4) -> None:
        if not 1 <= concurrency <= maximum_concurrency:
            raise DomainValidationError(
                f"Book chapter concurrency must be between 1 and {maximum_concurrency}"
            )
        self.concurrency = concurrency

    def validate_plan(
        self, chapter_numbers: list[int], dependencies: dict[int, list[int]] | None = None
    ) -> dict[int, list[int]]:
        ordered = sorted(chapter_numbers)
        if not ordered or ordered != list(range(1, len(ordered) + 1)):
            raise DomainValidationError("Book chapter numbers must be continuous and start at one")
        graph = dependencies or {
            chapter: ([] if chapter == 1 else [chapter - 1]) for chapter in ordered
        }
        if set(graph) != set(ordered):
            raise DomainValidationError("Dependency graph must define every planned chapter")
        for chapter, required in graph.items():
            if chapter in required or any(item not in graph for item in required):
                raise DomainValidationError("Dependency graph contains an invalid chapter edge")
        indegree = {chapter: 0 for chapter in ordered}
        outgoing: dict[int, list[int]] = {chapter: [] for chapter in ordered}
        for chapter, required in graph.items():
            indegree[chapter] = len(required)
            for dependency in required:
                outgoing[dependency].append(chapter)
        queue = deque(chapter for chapter, count in indegree.items() if count == 0)
        visited = 0
        while queue:
            current = queue.popleft()
            visited += 1
            for child in outgoing[current]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if visited != len(graph):
            raise DomainValidationError("Chapter dependency graph contains a cycle")
        return {chapter: sorted(required) for chapter, required in sorted(graph.items())}

    def decide(
        self,
        *,
        mode: BookRunMode,
        chapter_numbers: list[int],
        chapter_status: dict[int, str],
        dependencies: dict[int, list[int]] | None = None,
        cancel_requested: bool = False,
        pause_requested: bool = False,
        continue_after_needs_review: bool = False,
    ) -> ChapterScheduleDecision:
        graph = self.validate_plan(chapter_numbers, dependencies)
        if cancel_requested:
            return ChapterScheduleDecision(
                action="cancel", reason="Book cancellation was requested", dependency_status={}
            )
        if pause_requested:
            return ChapterScheduleDecision(
                action="pause", reason="Book pause was requested", dependency_status={}
            )
        if any(status in self._ACTIVE for status in chapter_status.values()):
            return ChapterScheduleDecision(
                action="wait",
                reason="A chapter job is still active",
                dependency_status=dict(sorted(chapter_status.items())),
            )
        if all(chapter_status.get(chapter) in self._DONE for chapter in chapter_numbers):
            return ChapterScheduleDecision(
                action="complete",
                reason="Every planned chapter has an accepted version",
                dependency_status=dict(sorted(chapter_status.items())),
            )
        if (
            any(status == "needs_review" for status in chapter_status.values())
            and not continue_after_needs_review
        ):
            chapter = min(
                number for number, status in chapter_status.items() if status == "needs_review"
            )
            return ChapterScheduleDecision(
                chapter_number=chapter,
                action="human_review",
                reason="A chapter reached its revision limit",
                dependency_status=dict(sorted(chapter_status.items())),
            )
        candidates: list[int] = []
        for chapter in sorted(chapter_numbers):
            if chapter_status.get(chapter) in self._DONE:
                continue
            if all(chapter_status.get(required) in self._DONE for required in graph[chapter]):
                candidates.append(chapter)
        if mode is BookRunMode.SEQUENTIAL:
            candidates = candidates[:1]
        else:
            candidates = candidates[: self.concurrency]
        if not candidates:
            return ChapterScheduleDecision(
                action="wait",
                reason="No chapter has all dependencies accepted",
                dependency_status=dict(sorted(chapter_status.items())),
            )
        return ChapterScheduleDecision(
            chapter_number=candidates[0],
            action="schedule",
            reason="All required predecessor chapters are accepted",
            dependency_status={
                required: chapter_status.get(required, "missing")
                for required in graph[candidates[0]]
            },
        )
