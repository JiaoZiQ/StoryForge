"""Rule graph, query planning, fusion, and reranking coverage."""

from __future__ import annotations

import pytest

from storyforge.enums import GraphEntityType, GraphPredicate
from storyforge.graph import GraphEntityNormalizer, GraphExtractor
from storyforge.models import Fact
from storyforge.retrieval import (
    HybridRetrievalRequest,
    HybridRetriever,
    HybridWeights,
    Reranker,
    RetrievalError,
    RetrievalHit,
    RetrievalQueryBuilder,
    RetrievalSource,
)
from storyforge.schemas.context import ChapterOutlineContext


def _hit(
    hit_id: int,
    source: RetrievalSource,
    *,
    content: str = "Mara carries the brass key",
    chapter: int = 1,
    status: str = "accepted",
) -> RetrievalHit:
    return RetrievalHit(
        id=hit_id,
        source=source,
        matched_sources=[source],
        source_type="fact" if source is RetrievalSource.FACT else "chapter_content",
        content=content,
        score=0.7,
        raw_score=0.7,
        project_id=1,
        chapter_number=chapter,
        version_id=2,
        entity_names=["Mara"],
        metadata={"status": status, "content_hash": "same"},
        explanation=f"{source.value} evidence",
    )


def test_graph_normalizer_is_conservative_and_disambiguates_explicit_roles() -> None:
    normalizer = GraphEntityNormalizer()
    assert normalizer.normalize("  M\uff21\uff32\uff21\uff0cVale\uff01 ") == "maravale"
    assert normalizer.normalize("Mara Vale") != normalizer.normalize("Mara Vales")
    assert (
        normalizer.disambiguation_key(entity_type="character", description="role: captain")
        == "character:captain"
    )
    assert normalizer.disambiguation_key(entity_type="character", description="A captain") == ""


def test_graph_extractor_uses_accepted_fact_evidence_and_controlled_predicate() -> None:
    content = "Mara lifted the brass key beside the gate."
    fact = Fact(
        project_id=1,
        chapter_id=1,
        chapter_version_id=1,
        normalized_hash="a" * 64,
        subject="Mara",
        predicate="owns",
        object="brass key",
        fact_type="object_state",
        confidence=0.95,
        source_quote="Mara lifted the brass key",
        valid_from_chapter=1,
    )
    result = GraphExtractor().extract(
        [fact],
        chapter_number=1,
        content=content,
        character_names={"Mara"},
        location_names=set(),
    )
    assert [item.entity_type for item in result.entities] == [
        GraphEntityType.CHARACTER,
        GraphEntityType.OBJECT,
    ]
    assert result.relations[0].predicate is GraphPredicate.OWNS
    assert result.relations[0].evidence in content
    fact.source_quote = "invented evidence"
    assert (
        not GraphExtractor()
        .extract(
            [fact],
            chapter_number=1,
            content=content,
            character_names={"Mara"},
            location_names=set(),
        )
        .relations
    )


def test_query_builder_is_bounded_deterministic_and_excludes_forbidden_reveal() -> None:
    outline = ChapterOutlineContext(
        chapter_number=2,
        title="The gate",
        objective="Mara opens the gate without naming the traitor",
        summary="A cautious crossing.",
        key_events=["Mara uses the brass key", "The traitor is named"],
        participating_characters=["Mara"],
        locations=["Harbor"],
        required_facts=["brass key"],
        forbidden_reveals=["traitor"],
        setup_foreshadowing=[],
        payoff_foreshadowing=[],
        ending_hook="The bell rings.",
    )
    plan = RetrievalQueryBuilder(max_query_chars=80).build(outline)
    assert "traitor" not in plan.semantic_query.casefold()
    assert len(plan.semantic_query) <= 80
    assert plan == RetrievalQueryBuilder(max_query_chars=80).build(outline)
    assert plan.character_names == ["Mara"]


def test_hybrid_fuses_deduplicates_filters_and_degrades_deterministically() -> None:
    def keyword(_: HybridRetrievalRequest) -> list[RetrievalHit]:
        return [
            _hit(1, RetrievalSource.KEYWORD),
            _hit(2, RetrievalSource.KEYWORD, content="future", chapter=2),
            _hit(3, RetrievalSource.KEYWORD, content="candidate", status="candidate"),
        ]

    def unavailable(_: HybridRetrievalRequest) -> list[RetrievalHit]:
        raise RuntimeError("offline")

    retriever = HybridRetriever(
        keyword=keyword,
        vector=unavailable,
        fact=lambda _: [_hit(9, RetrievalSource.FACT)],
        graph=lambda _: [_hit(4, RetrievalSource.GRAPH, content="Mara OWNS key")],
    )
    request = HybridRetrievalRequest(
        project_id=1,
        query="Mara key",
        current_chapter=2,
        character_names=["Mara"],
        top_k=5,
        max_context_chars=1_000,
    )
    result = retriever.retrieve(request)
    assert result.degraded is True
    assert result.degraded_reasons == ["vector_unavailable"]
    assert all(item.chapter_number is None or item.chapter_number < 2 for item in result.hits)
    assert all(item.metadata.get("status") == "accepted" for item in result.hits)
    assert result.deduplicated_count == 2
    assert {source for hit in result.hits for source in hit.matched_sources} == {
        RetrievalSource.FACT,
        RetrievalSource.GRAPH,
        RetrievalSource.KEYWORD,
    }
    assert retriever.retrieve(request) == result


def test_hybrid_all_routes_failed_weights_and_budget() -> None:
    def failed(_: HybridRetrievalRequest) -> list[RetrievalHit]:
        raise RuntimeError("failed")

    retriever = HybridRetriever(keyword=failed, vector=failed, fact=failed, graph=failed)
    request = HybridRetrievalRequest(project_id=1, query="key", current_chapter=2)
    with pytest.raises(RetrievalError, match="All"):
        retriever.retrieve(request)
    with pytest.raises(ValueError, match="sum"):
        HybridWeights(keyword=1, vector=1, fact=0, graph=0)
    budgeted = HybridRetriever(
        keyword=lambda _: [_hit(1, RetrievalSource.KEYWORD, content="x" * 200)],
        vector=lambda _: [],
        fact=lambda _: [],
        graph=lambda _: [],
    ).retrieve(request.model_copy(update={"max_context_chars": 100}))
    assert budgeted.hits == []
    assert budgeted.omitted_count == 1


def test_reranker_boosts_current_entities_and_penalizes_long_content() -> None:
    request = HybridRetrievalRequest(
        project_id=1,
        query="Mara",
        current_chapter=3,
        character_names=["Mara"],
    )
    short = _hit(1, RetrievalSource.FACT)
    long = _hit(2, RetrievalSource.VECTOR, content="x" * 1900)
    ranked = Reranker().rerank(request, [long, short])
    assert ranked[0].id == 1
    assert "current_character" in ranked[0].explanation
