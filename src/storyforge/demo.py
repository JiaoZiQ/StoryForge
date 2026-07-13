"""Deterministic milestone-three data used by the offline CLI and tests."""

# ruff: noqa: RUF001 -- Chinese prose intentionally uses Chinese punctuation.

from storyforge.enums import ConflictSeverity
from storyforge.evaluation.models import (
    ChapterCritique,
    CriticIssue,
    DimensionScore,
)
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
DEMO_EYE_QUOTE = "灯下，他天生的黑色眼睛映出一圈微弱的蓝光。"
DEMO_DEATH_QUOTE = "档案明确记载，旧守望者已于十年前死亡。"
CONFLICT_EYE_QUOTE = "林舟摘下护目镜，露出天生的蓝色眼睛。"
CONFLICT_WATCHER_QUOTE = "旧守望者从阴影里开口说话，命令林舟立即离开。"


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


def build_demo_provider(
    target_chapters: int,
    chapter_number: int = 1,
    *,
    include_canonical_attribute: bool = False,
    include_critical_setup: bool = False,
) -> MockLLMProvider:
    """Register deterministic structured responses for all three M3 agents."""
    content = "\n\n".join(
        (
            "海雾贴着旧港灯塔的铁门缓慢移动，锈蚀铰链在风里发出断续的低鸣。"
            "林舟调查旧港灯塔时，没有立刻推门，而是先记录潮线留下的盐痕。",
            "门后的齿轮竟仍在转动，细小震颤沿楼梯扶手传到他的指尖。"
            "他比对档案里的旧图，确认这套停用十年的机械刚刚重新启动。",
            f"{DEMO_QUOTE}{DEMO_EYE_QUOTE}潮汐纹铜钥匙改变了调查方向，钥匙齿与地下机房"
            "的封锁编号完全吻合，却少了一道应该存在的磨损。",
            "“先别碰主轴。”林舟对守门人说。他压低声音，逐项抄下压力表读数，"
            "随后用粉笔标记安全路线；短暂的沉默之后，海水从墙缝渗入，齿轮声骤然加快。",
            "林舟最终没有打开地下机房。他把现场照片和刻痕编号一并封存，决定先查清"
            f"钥匙的上一任持有人。{DEMO_DEATH_QUOTE}离开前，航海日志的最后一页在风中"
            "翻起，露出父亲名字的首字。",
        )
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
    facts = [
        ExtractedFact(
            subject="林舟",
            predicate="持有",
            object="潮汐纹铜钥匙",
            fact_type="possession",
            confidence=0.98,
            source_quote=DEMO_QUOTE,
            valid_from_chapter=chapter_number,
        )
    ]
    if include_canonical_attribute:
        facts.append(
            ExtractedFact(
                subject="林舟",
                predicate="eye_color",
                object="black",
                fact_type="character_attribute",
                confidence=0.99,
                source_quote=DEMO_EYE_QUOTE,
                valid_from_chapter=chapter_number,
            )
        )
    if include_critical_setup:
        facts.append(
            ExtractedFact(
                subject="旧守望者",
                predicate="state",
                object="dead",
                fact_type="character_state",
                confidence=0.99,
                source_quote=DEMO_DEATH_QUOTE,
                valid_from_chapter=chapter_number,
            )
        )
    extraction = FactExtractionResult(
        facts=facts,
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


def build_conflict_generation_provider(chapter_number: int = 2) -> MockLLMProvider:
    """Build a deterministic chapter with high and critical consistency conflicts."""
    content = "\n\n".join(
        (
            "清晨的档案室没有开灯，林舟沿着昨夜留下的编号查找旧港值班记录。"
            "纸页受潮发脆，他仍逐格核对签名，并找到了钥匙交接栏里的空白。",
            f"{CONFLICT_EYE_QUOTE}他把铜钥匙放在冷光灯下，确认凹槽里藏着一串"
            "被盐结晶覆盖的坐标；这条线索迫使调查转向废弃船坞。",
            "“记录上有人抹掉了名字。”他说。管理员没有回答，只把一只封存盒推到"
            f"桌面中央；盒中的潮汐图与灯塔压力表在同一时刻出现异常。{CONFLICT_WATCHER_QUOTE}",
            "林舟调查旧港灯塔留下的资料，并确认潮汐纹铜钥匙改变了调查方向。"
            "他没有越过封锁线，而是申请调取下一批航海日志。",
        )
    )
    draft = ChapterDraft(
        title=f"第{chapter_number}章 被删去的名字",
        content=content,
        summary="林舟从值班记录中找到被抹去的交接信息，却出现与既有事实冲突的外貌描述。",
        style_self_check=StyleSelfCheck(
            follows_outline=True,
            avoids_forbidden_reveals=True,
        ),
    )
    extraction = FactExtractionResult(
        facts=[
            ExtractedFact(
                subject="林舟",
                predicate="eye_color",
                object="blue",
                fact_type="character_attribute",
                confidence=0.99,
                source_quote=CONFLICT_EYE_QUOTE,
                valid_from_chapter=chapter_number,
            ),
            ExtractedFact(
                subject="旧守望者",
                predicate="speaks",
                object="warning",
                fact_type="action",
                confidence=0.99,
                source_quote=CONFLICT_WATCHER_QUOTE,
                valid_from_chapter=chapter_number,
            ),
        ]
    )
    return MockLLMProvider({ChapterDraft: draft, FactExtractionResult: extraction})


def _dimension(score: float, rationale: str) -> DimensionScore:
    return DimensionScore(score=score, rationale=rationale)


def build_critic_provider(scenario: str = "normal") -> MockLLMProvider:
    """Build deterministic critic output for normal and required failure scenarios."""
    if scenario == "normal":
        critique = ChapterCritique(
            prose=_dimension(8.4, "Clear, restrained imagery supports the viewpoint."),
            plot=_dimension(8.2, "The clue advances the investigation."),
            character=_dimension(8.0, "The protagonist acts consistently with the plan."),
            pacing=_dimension(7.8, "Observation and discovery remain balanced."),
            dialogue=_dimension(7.5, "Brief dialogue has a clear function."),
            emotional_impact=_dimension(7.8, "The final family hint adds emotional pressure."),
            consistency=_dimension(9.0, "No material continuity problem is present."),
            outline_adherence=_dimension(8.5, "Required events are represented."),
            overall_score=8.2,
            strengths=["Controlled atmosphere", "Actionable closing hook"],
            issues=[
                CriticIssue(
                    code="CRITIC_MINOR_TRANSITION",
                    category="pacing",
                    severity=ConflictSeverity.LOW,
                    description="One transition could be slightly clearer.",
                    suggestion="Clarify the transition without expanding the scene.",
                )
            ],
            revision_priorities=[],
            pass_recommendation=True,
        )
    elif scenario == "death":
        critique = ChapterCritique(
            prose=_dimension(6.5, "The prose remains readable."),
            plot=_dimension(5.5, "The action conflicts with established state."),
            character=_dimension(4.5, "A dead character acts without explanation."),
            pacing=_dimension(6.0, "The scene moves efficiently."),
            dialogue=_dimension(5.5, "Dialogue is functional."),
            emotional_impact=_dimension(5.0, "The contradiction weakens the impact."),
            consistency=_dimension(2.0, "A critical character-state conflict is present."),
            outline_adherence=_dimension(6.0, "Most planned events remain visible."),
            overall_score=5.1,
            strengths=["Readable scene construction"],
            issues=[
                CriticIssue(
                    code="CRITIC_DEAD_CHARACTER_ACTION",
                    category="consistency",
                    severity=ConflictSeverity.CRITICAL,
                    description="A character marked dead performs a present-time action.",
                    suggestion="Mark the scene as memory or establish resurrection first.",
                )
            ],
            revision_priorities=["CRITIC_DEAD_CHARACTER_ACTION"],
            pass_recommendation=False,
        )
    elif scenario == "outline":
        critique = ChapterCritique(
            prose=_dimension(6.8, "The prose is serviceable."),
            plot=_dimension(5.0, "The central planned event is absent."),
            character=_dimension(6.0, "Character behavior is plausible."),
            pacing=_dimension(5.8, "The scene spends time away from its objective."),
            dialogue=_dimension(6.0, "Dialogue is clear."),
            emotional_impact=_dimension(5.5, "The chapter lacks its planned turn."),
            consistency=_dimension(7.0, "No direct continuity contradiction is present."),
            outline_adherence=_dimension(3.0, "Required events are missing."),
            overall_score=5.6,
            strengths=["Readable prose"],
            issues=[
                CriticIssue(
                    code="CRITIC_OUTLINE_DRIFT",
                    category="outline",
                    severity=ConflictSeverity.HIGH,
                    description="The chapter omits a required outline event.",
                    suggestion="Restore the required event and its consequence.",
                )
            ],
            revision_priorities=["CRITIC_OUTLINE_DRIFT"],
            pass_recommendation=False,
        )
    elif scenario == "poor":
        critique = ChapterCritique(
            prose=_dimension(3.0, "Sentences are repetitive and vague."),
            plot=_dimension(5.0, "The plot advances only minimally."),
            character=_dimension(5.0, "Character intent is underdeveloped."),
            pacing=_dimension(3.5, "Repetition stalls the scene."),
            dialogue=_dimension(4.5, "Dialogue lacks distinct voice."),
            emotional_impact=_dimension(4.0, "The scene has little emotional escalation."),
            consistency=_dimension(7.0, "No major continuity problem is present."),
            outline_adherence=_dimension(6.0, "The outline is only partly realized."),
            overall_score=4.8,
            strengths=["The scene has a discernible objective"],
            issues=[
                CriticIssue(
                    code="CRITIC_FLAT_PROSE",
                    category="prose",
                    severity=ConflictSeverity.HIGH,
                    description="Repetitive phrasing weakens the prose and pacing.",
                    suggestion="Vary sentence structure and remove repeated observations.",
                )
            ],
            revision_priorities=["CRITIC_FLAT_PROSE"],
            pass_recommendation=False,
        )
    elif scenario == "conflict":
        critique = ChapterCritique(
            prose=_dimension(7.0, "The prose is controlled."),
            plot=_dimension(6.5, "The investigation advances."),
            character=_dimension(5.5, "The description contradicts prior canon."),
            pacing=_dimension(6.8, "The scene moves steadily."),
            dialogue=_dimension(6.5, "Dialogue is purposeful."),
            emotional_impact=_dimension(6.0, "The conflict distracts from the reveal."),
            consistency=_dimension(3.5, "A direct fact contradiction is present."),
            outline_adherence=_dimension(7.5, "Required events are represented."),
            overall_score=6.2,
            strengths=["Clear investigative progression"],
            issues=[
                CriticIssue(
                    code="CRITIC_FACT_CONTRADICTION",
                    category="consistency",
                    severity=ConflictSeverity.HIGH,
                    description="A character attribute contradicts established canon.",
                    suggestion="Restore the canonical attribute or explain the apparent change.",
                )
            ],
            revision_priorities=["CRITIC_FACT_CONTRADICTION"],
            pass_recommendation=False,
        )
    else:
        raise ValueError(f"Unknown critic mock scenario: {scenario}")
    return MockLLMProvider({ChapterCritique: critique})
