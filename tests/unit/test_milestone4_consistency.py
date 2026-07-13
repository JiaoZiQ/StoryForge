"""Deterministic milestone-four consistency rule tests."""

from storyforge.consistency import ConsistencyChecker
from storyforge.consistency.models import (
    ChapterOutlineEvidence,
    CharacterEvidence,
    CharacterStateUpdateEvidence,
    ConsistencyCheckRequest,
    FactEvidence,
    ForeshadowingEvidence,
    ForeshadowingUpdateEvidence,
    StoryRuleEvidence,
)
from storyforge.consistency.rules import (
    RULE_DEAD_CHARACTER_ACTION,
    RULE_EVENT_ORDER,
    RULE_FACT_CONTRADICTION,
    RULE_FORBIDDEN_REVEAL,
    RULE_FORESHADOW_EARLY,
    RULE_FORESHADOW_MISSING,
    RULE_FORESHADOW_REPEAT,
    RULE_FORESHADOW_UNSET,
    RULE_FUTURE_FACT,
    RULE_KNOWLEDGE_LEAK,
    RULE_LOCATION_CONFLICT,
    RULE_OBJECT_DESTROYED,
    RULE_OBJECT_POSSESSION,
    RULE_OUTLINE_MISSING,
    RULE_STORY_RULE,
)
from storyforge.enums import ConflictSeverity, ForeshadowingStatus


def _fact(
    subject: str,
    predicate: str,
    object_: str,
    *,
    chapter: int = 2,
    confidence: float = 1,
    fact_type: str = "event",
    fact_id: int | None = None,
) -> FactEvidence:
    return FactEvidence(
        fact_id=fact_id,
        subject=subject,
        predicate=predicate,
        object=object_,
        fact_type=fact_type,
        confidence=confidence,
        source_quote=f"{subject}-{predicate}-{object_}",
        chapter_number=chapter,
        valid_from_chapter=chapter,
    )


def _request(**changes: object) -> ConsistencyCheckRequest:
    values: dict[str, object] = {
        "project_id": 1,
        "chapter_id": 2,
        "chapter_number": 2,
        "content": "林舟调查旧港灯塔。",
        "new_facts": [],
        "historical_facts": [],
        "characters": [],
        "story_rules": [],
        "outline": ChapterOutlineEvidence(),
        "active_foreshadowing": [],
        "foreshadowing_updates": [],
    }
    values.update(changes)
    return ConsistencyCheckRequest.model_validate(values)


def _codes(request: ConsistencyCheckRequest) -> set[str]:
    return {item.rule_code for item in ConsistencyChecker().check(request).conflicts}


def test_direct_fact_conflict_and_identical_fact_behavior() -> None:
    old = _fact("林舟", "eye_color", "black", chapter=1, fact_id=10)
    conflict = ConsistencyChecker().check(
        _request(new_facts=[_fact(" 林舟 ", "EYE_COLOR", "blue")], historical_facts=[old])
    )
    assert conflict.conflicts[0].rule_code == RULE_FACT_CONTRADICTION
    assert conflict.conflicts[0].existing_fact_id == 10
    assert conflict.conflicts[0].severity is ConflictSeverity.HIGH

    same = _request(new_facts=[_fact("林舟", "eye_color", "BLACK")], historical_facts=[old])
    assert RULE_FACT_CONTRADICTION not in _codes(same)


def test_dead_character_action_and_non_present_scenes() -> None:
    character = CharacterEvidence(name="林舟", current_state="dead")
    action = _fact("林舟", "walks", "harbor")
    result = ConsistencyChecker().check(_request(new_facts=[action], characters=[character]))
    assert result.conflicts[0].rule_code == RULE_DEAD_CHARACTER_ACTION
    assert result.conflicts[0].severity is ConflictSeverity.CRITICAL

    for scene_type in ("memory", "dream", "quotation", "corpse"):
        remembered = action.model_copy(update={"fact_type": scene_type})
        assert RULE_DEAD_CHARACTER_ACTION not in _codes(
            _request(new_facts=[remembered], characters=[character])
        )

    resurrection = StoryRuleEvidence(
        rule_id=1,
        category="world",
        statement="Resurrection is possible.",
        structured_metadata={"allows_resurrection": True},
    )
    assert RULE_DEAD_CHARACTER_ACTION not in _codes(
        _request(new_facts=[action], characters=[character], story_rules=[resurrection])
    )

    update = CharacterStateUpdateEvidence(
        character_name="林舟",
        field="current_state",
        value="死亡",
        confidence=1,
    )
    assert RULE_DEAD_CHARACTER_ACTION in _codes(
        _request(new_facts=[action], character_updates=[update])
    )


def test_low_confidence_match_cannot_create_critical_conflict() -> None:
    result = ConsistencyChecker().check(
        _request(
            new_facts=[_fact("林舟", "speaks", "warning", confidence=0.3)],
            characters=[CharacterEvidence(name="林舟", current_state="死亡")],
        )
    )
    assert result.conflicts[0].severity is ConflictSeverity.HIGH


def test_location_conflict_requires_missing_transition() -> None:
    locations = [
        _fact("林舟", "is_at", "harbor"),
        _fact("林舟", "located_at", "tower"),
    ]
    assert RULE_LOCATION_CONFLICT in _codes(_request(new_facts=locations))
    assert RULE_LOCATION_CONFLICT not in _codes(
        _request(new_facts=[*locations, _fact("林舟", "travels", "tower")])
    )


def test_knowledge_leak_and_revealed_secret() -> None:
    character = CharacterEvidence(
        name="Mara",
        current_state="active",
        secrets=["sealed letter"],
    )
    knows = _fact("Mara", "knows", "sealed letter")
    assert RULE_KNOWLEDGE_LEAK in _codes(_request(new_facts=[knows], characters=[character]))
    reveal = _fact("Mara", "revealed", "sealed letter", chapter=1)
    assert RULE_KNOWLEDGE_LEAK not in _codes(
        _request(new_facts=[knows], historical_facts=[reveal], characters=[character])
    )
    known_character = character.model_copy(update={"knowledge": ["sealed letter"]})
    assert RULE_KNOWLEDGE_LEAK not in _codes(
        _request(new_facts=[knows], characters=[known_character])
    )


def test_structured_story_rule_conflict() -> None:
    rule = StoryRuleEvidence(
        rule_id=1,
        category="magic",
        statement="Fire magic is forbidden in the city.",
        structured_metadata={"location": "city", "forbidden_predicates": ["uses_fire"]},
    )
    request = _request(
        new_facts=[
            _fact("Mara", "is_at", "city"),
            _fact("Mara", "uses_fire", "fireball"),
        ],
        story_rules=[rule],
    )
    assert RULE_STORY_RULE in _codes(request)


def test_destroyed_object_and_possession_transfer_rules() -> None:
    destroyed = _fact("sword", "state", "destroyed", chapter=1)
    used = _fact("Mara", "uses", "sword")
    assert RULE_OBJECT_DESTROYED in _codes(_request(new_facts=[used], historical_facts=[destroyed]))

    old_owner = _fact("Mara", "owns", "key", chapter=1)
    new_owner = _fact("Lin", "carries", "key")
    without_transfer = ConsistencyChecker().check(
        _request(new_facts=[new_owner], historical_facts=[old_owner])
    )
    assert any(item.rule_code == RULE_OBJECT_POSSESSION for item in without_transfer.conflicts)
    with_transfer = _request(
        new_facts=[_fact("Mara", "transfers", "key"), new_owner],
        historical_facts=[old_owner],
    )
    assert RULE_OBJECT_POSSESSION not in _codes(with_transfer)


def test_future_fact_and_event_order_rules() -> None:
    future = _fact("Mara", "knows", "ending", chapter=3)
    result = ConsistencyChecker().check(_request(new_facts=[future]))
    assert RULE_FUTURE_FACT in {item.rule_code for item in result.conflicts}

    ended = _fact("storm", "event_status", "ended", chapter=1)
    restarted = _fact("storm", "event_status", "not started")
    prior_order = _fact("voyage", "sequence", "5", chapter=1)
    backwards = _fact("voyage", "sequence", "4")
    codes = _codes(
        _request(
            new_facts=[restarted, backwards],
            historical_facts=[ended, prior_order],
        )
    )
    assert RULE_EVENT_ORDER in codes


def test_outline_missing_and_forbidden_reveal() -> None:
    missing = _request(
        content="Only fog appears.",
        outline=ChapterOutlineEvidence(key_events=["Mara opens the gate"]),
    )
    assert RULE_OUTLINE_MISSING in _codes(missing)

    reveal = _request(
        content="The keeper is Mara's father.",
        outline=ChapterOutlineEvidence(forbidden_reveals=["keeper is Mara's father"]),
    )
    assert RULE_FORBIDDEN_REVEAL in _codes(reveal)


def test_foreshadowing_early_repeat_missing_and_unset() -> None:
    early = ForeshadowingEvidence(
        foreshadowing_id=1,
        description="the key",
        setup_chapter=2,
        expected_payoff_chapter=3,
        payoff_chapter=1,
        status=ForeshadowingStatus.RESOLVED,
    )
    assert RULE_FORESHADOW_EARLY in _codes(_request(active_foreshadowing=[early]))

    resolved = early.model_copy(update={"setup_chapter": 1, "payoff_chapter": 1})
    repeat = _request(
        active_foreshadowing=[resolved],
        outline=ChapterOutlineEvidence(payoff_foreshadowing=["the key"]),
    )
    assert RULE_FORESHADOW_REPEAT in _codes(repeat)

    open_record = resolved.model_copy(
        update={"status": ForeshadowingStatus.OPEN, "payoff_chapter": None}
    )
    missing = _request(
        active_foreshadowing=[open_record],
        outline=ChapterOutlineEvidence(payoff_foreshadowing=["the key"]),
    )
    assert RULE_FORESHADOW_MISSING in _codes(missing)

    unset = _request(
        foreshadowing_updates=[
            ForeshadowingUpdateEvidence(action="resolve", description="unknown", confidence=1)
        ]
    )
    assert RULE_FORESHADOW_UNSET in _codes(unset)

    resolved_now = _request(
        active_foreshadowing=[
            open_record.model_copy(
                update={
                    "status": ForeshadowingStatus.RESOLVED,
                    "payoff_chapter": 2,
                }
            )
        ],
        foreshadowing_updates=[
            ForeshadowingUpdateEvidence(
                action="resolve",
                description="the key",
                foreshadowing_id=1,
                confidence=1,
            )
        ],
        outline=ChapterOutlineEvidence(payoff_foreshadowing=["the key"]),
    )
    assert RULE_FORESHADOW_REPEAT not in _codes(resolved_now)
    assert RULE_FORESHADOW_MISSING not in _codes(resolved_now)


def test_consistency_score_and_counts_are_bounded_and_stable() -> None:
    result = ConsistencyChecker().check(
        _request(
            new_facts=[_fact("林舟", "walks", "harbor")],
            characters=[CharacterEvidence(name="林舟", current_state="dead")],
        )
    )
    assert 0 <= result.score <= 10
    assert result.checked_rule_count == 10
    assert result.critical_count == 1
    assert result.high_count == result.medium_count == result.low_count == 0
    assert result.checker_version
