"""Mechanical M3 schema, prompt, and agent validation tests."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from storyforge.agents import FactExtractorAgent
from storyforge.demo import DEMO_QUOTE, build_demo_plan
from storyforge.llm import MockLLMProvider
from storyforge.prompts import PROMPT_VERSION, build_prompt_registry
from storyforge.schemas.generation import (
    CharacterStateUpdate,
    ExtractedFact,
    FactExtractionRequest,
    FactExtractionResult,
    ForeshadowingUpdate,
)
from storyforge.schemas.planning import NovelPlan


def test_novel_plan_rejects_duplicate_names_gaps_and_unknown_references() -> None:
    valid = build_demo_plan(3).model_dump()

    duplicate = deepcopy(valid)
    duplicate["characters"].append(deepcopy(duplicate["characters"][0]))
    with pytest.raises(ValidationError, match="character names must be unique"):
        NovelPlan.model_validate(duplicate)

    gap = deepcopy(valid)
    gap["chapter_plans"][1]["chapter_number"] = 3
    with pytest.raises(ValidationError, match="consecutive"):
        NovelPlan.model_validate(gap)

    unknown = deepcopy(valid)
    unknown["chapter_plans"][0]["locations"] = ["未知地点"]
    with pytest.raises(ValidationError, match="unknown chapter locations"):
        NovelPlan.model_validate(unknown)


def test_fact_extractor_filters_duplicates_low_confidence_future_and_bad_quotes() -> None:
    valid = ExtractedFact(
        subject="林舟",
        predicate="持有",
        object="铜钥匙",
        fact_type="possession",
        confidence=0.9,
        source_quote=DEMO_QUOTE,
        valid_from_chapter=1,
    )
    low = valid.model_copy(update={"object": "低置信事实", "confidence": 0.2})
    future = valid.model_copy(update={"object": "未来事实", "valid_from_chapter": 2})
    bad_quote = valid.model_copy(update={"object": "无引文事实", "source_quote": "不在正文"})
    response = FactExtractionResult(
        facts=[valid, valid, low, future, bad_quote],
        character_updates=[
            CharacterStateUpdate(
                character_name="林舟",
                field="current_state",
                value="拿到钥匙",
                confidence=0.9,
                source_quote=DEMO_QUOTE,
            ),
            CharacterStateUpdate(
                character_name="林舟",
                field="current_state",
                value="不可信",
                confidence=0.1,
                source_quote=DEMO_QUOTE,
            ),
        ],
        foreshadowing_updates=[
            ForeshadowingUpdate(
                action="setup",
                description="钥匙伏笔",
                confidence=0.9,
                source_quote="不在正文",
            )
        ],
    )
    provider = MockLLMProvider({FactExtractionResult: response})
    result = FactExtractorAgent(provider, build_prompt_registry()).extract(
        FactExtractionRequest(
            project_id=1,
            chapter_number=1,
            chapter_content=f"开头。{DEMO_QUOTE}结尾。",
            context_summary="林舟进入灯塔。",
        )
    )

    assert result.output.facts == [valid]
    assert len(result.output.character_updates) == 1
    assert result.output.foreshadowing_updates == []
    assert result.prompt_versions == {
        "fact_extractor.system": PROMPT_VERSION,
        "fact_extractor.user": PROMPT_VERSION,
    }


def test_prompt_catalog_contains_separate_versioned_system_and_user_templates() -> None:
    registry = build_prompt_registry()

    for agent in ("planner", "writer", "fact_extractor"):
        assert registry.versions(f"{agent}.system") == (PROMPT_VERSION,)
        assert registry.versions(f"{agent}.user") == (PROMPT_VERSION,)
