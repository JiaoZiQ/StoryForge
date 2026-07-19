"""Bounded, deterministic targeted-revision planning."""

from __future__ import annotations

from decimal import Decimal

from storyforge.book.models import (
    BookCritique,
    BookEvaluationResult,
    BookIssue,
    BookRevisionPlanData,
    ChapterRevisionTaskData,
)

_CATEGORY_RANK = {
    "timeline": 1,
    "knowledge": 2,
    "ending": 3,
    "foreshadowing": 4,
    "character": 5,
    "transition": 6,
    "pacing": 7,
    "repetition": 8,
}
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class BookRevisionPlanner:
    """Select a small, dependency-ordered set of chapters for one revision round."""

    def __init__(
        self, *, maximum_chapters: int = 3, estimated_tokens_per_chapter: int = 12_000
    ) -> None:
        if maximum_chapters < 1:
            raise ValueError("A revision round must allow at least one chapter")
        self.maximum_chapters = maximum_chapters
        self.estimated_tokens_per_chapter = estimated_tokens_per_chapter

    def build(
        self,
        *,
        snapshot_id: int,
        revision_round: int,
        total_chapters: int,
        evaluation: BookEvaluationResult,
        critique: BookCritique,
        remaining_calls: int,
        remaining_tokens: int,
        remaining_cost: Decimal,
        per_call_cost: Decimal = Decimal("0"),
        preserve_facts: list[str] | None = None,
    ) -> BookRevisionPlanData:
        issues = sorted(
            critique.global_issues,
            key=lambda item: (
                _SEVERITY_RANK[item.severity],
                _CATEGORY_RANK.get(item.category.casefold(), 99),
                min(item.chapter_numbers, default=total_chapters + 1),
                item.code,
            ),
        )
        grouped: dict[int, list[BookIssue]] = {}
        for issue in issues:
            for chapter in issue.chapter_numbers:
                grouped.setdefault(chapter, []).append(issue)
        ordered_chapters = sorted(
            grouped,
            key=lambda chapter: (
                min(_SEVERITY_RANK[item.severity] for item in grouped[chapter]),
                chapter,
            ),
        )
        call_limit = min(self.maximum_chapters, max(0, remaining_calls))
        token_limit = remaining_tokens // self.estimated_tokens_per_chapter
        cost_limit = (
            int(remaining_cost // per_call_cost) if per_call_cost > 0 else self.maximum_chapters
        )
        selected = ordered_chapters[: min(call_limit, token_limit, cost_limit)]
        tasks: list[ChapterRevisionTaskData] = []
        for order, chapter in enumerate(selected, start=1):
            chapter_issues = grouped[chapter]
            codes = sorted({item.code for item in chapter_issues})
            required = [item.suggestion for item in chapter_issues][:5]
            future = list(range(chapter + 1, total_chapters + 1))
            categories = sorted({item.category for item in chapter_issues})
            tasks.append(
                ChapterRevisionTaskData(
                    chapter_number=chapter,
                    priority=order,
                    issue_codes=codes,
                    objective="; ".join(item.description for item in chapter_issues[:2]),
                    required_changes=required,
                    preserve_facts=list(preserve_facts or []),
                    affected_future_chapters=future,
                    rerun_global_checks=categories or ["timeline", "character"],
                )
            )
        objectives = [reason for reason in evaluation.blocking_reasons if reason][:5] or [
            "Resolve the highest-priority global issues without changing accepted canon."
        ]
        return BookRevisionPlanData(
            book_snapshot_id=snapshot_id,
            revision_round=revision_round,
            global_objectives=objectives,
            chapter_tasks=tasks,
            dependency_order=[item.chapter_number for item in tasks],
            must_preserve=list(preserve_facts or []),
            global_constraints=[
                "Do not use future chapter facts while revising an earlier chapter.",
                "Do not replace accepted history until the revised version passes evaluation.",
                "Recheck every affected later chapter after an earlier chapter changes.",
            ],
            estimated_calls=len(tasks),
            estimated_tokens=len(tasks) * self.estimated_tokens_per_chapter,
            estimated_cost=per_call_cost * len(tasks),
        )
