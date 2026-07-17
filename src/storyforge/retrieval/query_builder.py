"""Rule-based retrieval plans built only from current, writer-visible context."""

from storyforge.retrieval.models import RetrievalQueryPlan
from storyforge.schemas.context import ChapterOutlineContext


class RetrievalQueryBuilder:
    """Build deterministic bounded queries without an additional model call."""

    def __init__(self, *, max_query_chars: int = 1500) -> None:
        self.max_query_chars = max_query_chars

    def build(
        self,
        outline: ChapterOutlineContext,
        *,
        previous_summary: str = "",
        active_foreshadowing: list[str] | None = None,
    ) -> RetrievalQueryPlan:
        forbidden = {item.casefold() for item in outline.forbidden_reveals}
        candidates = [
            outline.objective,
            *outline.key_events,
            *outline.required_facts,
            *outline.participating_characters,
            *outline.locations,
            *(active_foreshadowing or []),
            previous_summary,
        ]
        safe = [
            item.strip()
            for item in candidates
            if item.strip() and not any(secret in item.casefold() for secret in forbidden)
        ]
        semantic = " | ".join(dict.fromkeys(safe))[: self.max_query_chars].strip(" |")
        if not semantic:
            semantic = outline.objective[: self.max_query_chars]
        keywords = list(
            dict.fromkeys(
                [
                    *outline.participating_characters,
                    *outline.locations,
                    *outline.required_facts,
                ]
            )
        )
        return RetrievalQueryPlan(
            semantic_query=semantic,
            keywords=keywords[:20],
            character_names=outline.participating_characters,
            location_names=outline.locations,
            relation_types=[],
            source_types=[
                "chapter_content",
                "chapter_summary",
                "fact",
                "character",
                "location",
                "story_rule",
                "foreshadowing",
                "graph_relation",
            ],
        )
