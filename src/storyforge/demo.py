"""Deterministic milestone-three data used by the offline CLI and tests."""

# ruff: noqa: RUF001 -- Chinese prose intentionally uses Chinese punctuation.

from storyforge.llm import MockLLMProvider
from storyforge.schemas.generation import (
    ChapterDraft,
    CharacterStateUpdate,
    ExtractedFact,
    FactExtractionResult,
    ForeshadowingUpdate,
    StyleSelfCheck,
)
from storyforge.schemas.planning import (
    ChapterPlan,
    CharacterPlan,
    ForeshadowingPlan,
    LocationPlan,
    NovelPlan,
    StoryRulePlan,
)

DEMO_QUOTE = "林舟把刻有潮汐纹的铜钥匙收入外套内袋。"


def build_demo_plan(target_chapters: int) -> NovelPlan:
    """Build a complete deterministic plan matching an arbitrary positive target."""
    chapters = []
    for number in range(1, target_chapters + 1):
        final = number == target_chapters
        chapters.append(
            ChapterPlan(
                chapter_number=number,
                title=f"第{number}章 潮汐回声",
                objective=(
                    "揭示灯塔失踪事件的真相并完成主角选择"
                    if final
                    else "让林舟获得一条关于失踪灯塔的新线索"
                ),
                summary=(
                    "林舟在旧港灯塔面对真相，决定公开航海日志。"
                    if final
                    else "林舟进入旧港灯塔，发现潮汐纹铜钥匙与残缺航海日志。"
                ),
                key_events=["林舟调查旧港灯塔", "潮汐纹铜钥匙改变了调查方向"],
                participating_characters=["林舟"],
                locations=["旧港灯塔"],
                required_facts=[] if number == 1 else ["林舟持有潮汐纹铜钥匙"],
                forbidden_reveals=[] if final else ["不要提前揭示灯塔守望者的最终去向"],
                setup_foreshadowing=["潮汐纹铜钥匙"] if number == 1 else [],
                payoff_foreshadowing=["潮汐纹铜钥匙"] if final else [],
                ending_hook="航海日志的最后一页写着林舟父亲的名字。",
            )
        )
    return NovelPlan(
        logline="一名档案修复师追查会随潮汐消失的灯塔，并重新选择与故乡的关系。",
        themes=["记忆", "选择", "故乡"],
        world_summary="近海城市雾岬保存着由潮汐驱动的旧式灯塔网络。",
        central_conflict="林舟必须在保护家族秘密与拯救港口之间作出选择。",
        ending_direction="失踪事件被公开，灯塔恢复运作，林舟选择留在雾岬。",
        style_guide="使用克制的第三人称限知叙事，以海雾和机械声作为重复意象。",
        characters=[
            CharacterPlan(
                name="林舟",
                role="主角",
                description="谨慎的青年档案修复师。",
                goals=["查明灯塔失踪事件"],
                personality=["克制", "敏锐"],
                speech_style="句子简短，很少直接表达情绪。",
                initial_state="刚回到雾岬，对故乡保持疏离。",
                secrets=["他尚未告诉任何人自己收到过父亲的匿名信。"],
            )
        ],
        locations=[
            LocationPlan(
                name="旧港灯塔",
                description="停用十年的铸铁灯塔，内部仍有潮汐机械运转。",
                rules=["涨潮后地下机房才会开启"],
            )
        ],
        story_rules=[
            StoryRulePlan(
                category="world",
                statement="潮汐机械只能在真实海水接触时运转。",
            )
        ],
        chapter_plans=chapters,
        foreshadowing=[
            ForeshadowingPlan(
                description="潮汐纹铜钥匙会开启地下机房。",
                setup_chapter=1,
                expected_payoff_chapter=target_chapters,
                importance="high",
            )
        ],
    )


def build_demo_provider(target_chapters: int, chapter_number: int = 1) -> MockLLMProvider:
    """Register deterministic structured responses for all three M3 agents."""
    content = (
        "海雾贴着旧港灯塔的铁门缓慢移动。林舟听见内部齿轮仍在转动。"
        f"{DEMO_QUOTE}他没有打开地下机房，而是先记下门锁上的刻痕。"
    )
    draft = ChapterDraft(
        title=f"第{chapter_number}章 潮汐回声",
        content=content,
        summary="林舟进入旧港灯塔并取得潮汐纹铜钥匙，调查出现新的方向。",
        style_self_check=StyleSelfCheck(
            follows_outline=True,
            avoids_forbidden_reveals=True,
        ),
    )
    extraction = FactExtractionResult(
        facts=[
            ExtractedFact(
                subject="林舟",
                predicate="持有",
                object="潮汐纹铜钥匙",
                fact_type="possession",
                confidence=0.98,
                source_quote=DEMO_QUOTE,
                valid_from_chapter=chapter_number,
            )
        ],
        character_updates=[
            CharacterStateUpdate(
                character_name="林舟",
                field="current_state",
                value="已进入旧港灯塔并取得潮汐纹铜钥匙。",
                confidence=0.95,
                source_quote=DEMO_QUOTE,
            )
        ],
        foreshadowing_updates=[
            ForeshadowingUpdate(
                action="setup",
                description="潮汐纹铜钥匙会开启地下机房。",
                confidence=0.9,
                source_quote=DEMO_QUOTE,
            )
        ],
    )
    return MockLLMProvider(
        {
            NovelPlan: build_demo_plan(target_chapters),
            ChapterDraft: draft,
            FactExtractionResult: extraction,
        }
    )
