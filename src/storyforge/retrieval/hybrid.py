"""Hybrid retrieval fusion, final isolation filtering and context budgeting."""

from __future__ import annotations

import re
from collections.abc import Callable

from storyforge.retrieval.models import (
    HybridRetrievalRequest,
    HybridRetrievalResult,
    HybridWeights,
    RetrievalError,
    RetrievalHit,
    RetrievalSource,
)
from storyforge.retrieval.reranker import Reranker

Retriever = Callable[[HybridRetrievalRequest], list[RetrievalHit]]
_NORMALIZE = re.compile(r"[^a-z0-9\u3400-\u4dbf\u4e00-\u9fff]+")


class HybridRetriever:
    """Combine four independent routes with weighted reciprocal rank fusion."""

    version = "hybrid-rrf-v1"

    def __init__(
        self,
        *,
        keyword: Retriever,
        vector: Retriever,
        fact: Retriever,
        graph: Retriever,
        weights: HybridWeights | None = None,
        reranker: Reranker | None = None,
        rrf_k: int = 60,
    ) -> None:
        self._retrievers = {
            RetrievalSource.KEYWORD: keyword,
            RetrievalSource.VECTOR: vector,
            RetrievalSource.FACT: fact,
            RetrievalSource.GRAPH: graph,
        }
        self.weights = weights or HybridWeights()
        self._reranker = reranker or Reranker()
        self.rrf_k = rrf_k

    def retrieve(self, request: HybridRetrievalRequest) -> HybridRetrievalResult:
        included = request.include_sources or list(RetrievalSource)
        per_source: dict[RetrievalSource, list[RetrievalHit]] = {}
        failures: list[str] = []
        for source in included:
            try:
                per_source[source] = self._retrievers[source](request)
            except Exception:
                failures.append(f"{source.value}_unavailable")
        if not per_source:
            raise RetrievalError("All configured retrieval routes failed")

        merged: dict[str, RetrievalHit] = {}
        fusion_scores: dict[str, float] = {}
        for source, hits in per_source.items():
            weight = float(getattr(self.weights, source.value))
            for rank, hit in enumerate(hits, start=1):
                if not self._visible(request, hit):
                    continue
                key = self._dedup_key(hit)
                fusion_scores[key] = fusion_scores.get(key, 0.0) + weight / (self.rrf_k + rank)
                if key not in merged:
                    merged[key] = hit
                else:
                    current = merged[key]
                    sources = sorted(
                        set((*current.matched_sources, *hit.matched_sources)),
                        key=lambda item: item.value,
                    )
                    merged[key] = current.model_copy(
                        update={
                            "matched_sources": sources,
                            "explanation": f"{current.explanation}; also {source.value}",
                        }
                    )
        max_score = max(fusion_scores.values(), default=1.0)
        fused = [
            hit.model_copy(update={"score": fusion_scores[key] / max_score})
            for key, hit in merged.items()
        ]
        reranked = self._reranker.rerank(request, fused)
        selected: list[RetrievalHit] = []
        estimated = 0
        for hit in reranked:
            if len(selected) >= request.top_k:
                break
            if estimated + len(hit.content) > request.max_context_chars:
                continue
            selected.append(hit)
            estimated += len(hit.content)
        counts = {source: len(per_source.get(source, [])) for source in RetrievalSource}
        total = sum(counts.values())
        return HybridRetrievalResult(
            query=request.query,
            hits=selected,
            total_candidates=total,
            keyword_candidates=counts[RetrievalSource.KEYWORD],
            vector_candidates=counts[RetrievalSource.VECTOR],
            fact_candidates=counts[RetrievalSource.FACT],
            graph_candidates=counts[RetrievalSource.GRAPH],
            deduplicated_count=len(merged),
            omitted_count=max(0, total - len(selected)),
            estimated_chars=estimated,
            retrieval_version=self.version,
            filters_applied=[
                "project_id",
                "accepted_status",
                "chapter_cutoff",
                "validity_interval",
                "context_budget",
            ],
            degraded=bool(failures),
            degraded_reasons=failures,
        )

    @staticmethod
    def _visible(request: HybridRetrievalRequest, hit: RetrievalHit) -> bool:
        status = hit.metadata.get("status")
        if status is not None and status != "accepted":
            return False
        if hit.project_id != request.project_id:
            return False
        return hit.chapter_number is None or hit.chapter_number < request.current_chapter

    @staticmethod
    def _dedup_key(hit: RetrievalHit) -> str:
        if hit.source_type == "fact":
            return f"fact:{_NORMALIZE.sub('', hit.content.casefold())}"
        canonical = hit.metadata.get("normalized_hash") or hit.metadata.get("content_hash")
        if canonical:
            return str(canonical)
        return _NORMALIZE.sub("", hit.content.casefold())
