"""Explainable, deterministic global analyzers for a frozen book snapshot."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from itertools import combinations, pairwise
from typing import Literal

from storyforge.book.models import (
    AcceptedFactData,
    ChapterPacingMetrics,
    ChapterTransitionResult,
    CharacterArcIssue,
    CharacterArcPointData,
    CharacterArcResult,
    CharacterProfileData,
    ForeshadowingAnalysisResult,
    ForeshadowingIssue,
    ForeshadowingItemData,
    KnowledgeBoundaryData,
    PacingAnalysisResult,
    PacingIssue,
    RelationshipPointData,
    RepetitionAnalysisResult,
    RepetitionCandidate,
    SnapshotChapter,
    TimelineAnalysisResult,
    TimelineConflict,
    TimelineEventData,
    TransitionIssue,
)

_ACTION_PREDICATES = frozenset(
    {
        "acts",
        "arrives",
        "attacks",
        "decides",
        "does",
        "leaves",
        "meets",
        "moves",
        "says",
        "travels",
        "uses",
        "walks",
        "行动",
        "到达",
        "攻击",
        "决定",
        "移动",
        "说话",
        "使用",
        "离开",
        "行走",
    }
)
_LOCATION_PREDICATES = frozenset({"located_at", "is_at", "location", "位于", "地点"})
_DEATH_VALUES = frozenset({"dead", "death", "died", "死亡", "已死"})
_DESTROYED_VALUES = frozenset({"destroyed", "broken", "毁坏", "销毁", "已毁"})
_KNOWLEDGE_PREDICATES = frozenset({"knows", "learned", "discovered", "知道", "获知", "发现"})
_RELATIONSHIP_PREDICATES = {
    "trusts": "trust",
    "friend": "friendship",
    "hostile_to": "hostility",
    "family_of": "family",
    "loves": "romance",
    "allied_with": "alliance",
    "mentors": "mentorship",
    "commands": "authority",
    "信任": "trust",
    "朋友": "friendship",
    "敌对": "hostility",
    "家人": "family",
    "爱慕": "romance",
    "同盟": "alliance",
    "指导": "mentorship",
    "领导": "authority",
}
_TIME_PATTERN = re.compile(r"(?:day|month|year|第)\s*(\d+)", re.IGNORECASE)


def _normalized(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", value.casefold(), flags=re.UNICODE)


def _bounded(value: str, limit: int = 160) -> str:
    collapsed = " ".join(value.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[: limit - 1]}…"


def _score(penalty: float) -> float:
    return round(max(0.0, min(10.0, 10.0 - penalty)), 2)


class TimelineAnalyzer:
    """Build accepted-fact events and check bounded temporal invariants."""

    version = "timeline-rules-v1"

    def analyze(self, facts: list[AcceptedFactData]) -> TimelineAnalysisResult:
        ordered = sorted(facts, key=lambda item: (item.chapter_number, item.id))
        events = [self._event(item, index) for index, item in enumerate(ordered)]
        conflicts: list[TimelineConflict] = []
        conflicts.extend(self._death_conflicts(ordered, events))
        conflicts.extend(self._location_conflicts(ordered, events))
        conflicts.extend(self._object_conflicts(ordered, events))
        conflicts.extend(self._numeric_time_conflicts(events))
        conflicts.extend(self._cause_conflicts(ordered, events))
        conflicts = self._deduplicate_conflicts(conflicts)
        penalty = sum(
            {"critical": 4.0, "high": 2.0, "medium": 0.8, "low": 0.25}[item.severity]
            for item in conflicts
        )
        return TimelineAnalysisResult(
            score=_score(penalty),
            events=events,
            conflicts=conflicts,
            checker_version=self.version,
        )

    @staticmethod
    def _event(fact: AcceptedFactData, index: int) -> TimelineEventData:
        raw = f"{fact.subject}|{fact.predicate}|{fact.object}|{fact.chapter_version_id}"
        key = hashlib.sha256(raw.encode()).hexdigest()[:24]
        story_time = fact.object if _normalized(fact.predicate) in {"storytime", "时间"} else None
        location = fact.object if _normalized(fact.predicate) in _LOCATION_PREDICATES else None
        return TimelineEventData(
            event_key=key,
            chapter_id=fact.chapter_id,
            chapter_version_id=fact.chapter_version_id,
            chapter_number=fact.chapter_number,
            title=f"{fact.subject} {fact.predicate}",
            description=f"{fact.subject} {fact.predicate} {fact.object}",
            story_time=story_time,
            sequence_index=index,
            location=location,
            participants=[fact.subject],
            confidence=fact.confidence,
            evidence=_bounded(fact.evidence),
        )

    def _death_conflicts(
        self, facts: list[AcceptedFactData], events: list[TimelineEventData]
    ) -> list[TimelineConflict]:
        deaths: dict[str, tuple[AcceptedFactData, TimelineEventData]] = {}
        result: list[TimelineConflict] = []
        for fact, event in zip(facts, events, strict=True):
            subject = _normalized(fact.subject)
            predicate = _normalized(fact.predicate)
            value = _normalized(fact.object)
            if predicate in {"status", "state", "alive", "生命状态", "状态"} and value in {
                _normalized(item) for item in _DEATH_VALUES
            }:
                deaths[subject] = (fact, event)
                continue
            if subject not in deaths or predicate not in {
                _normalized(p) for p in _ACTION_PREDICATES
            }:
                continue
            death, death_event = deaths[subject]
            if fact.chapter_number <= death.chapter_number:
                continue
            severity: Literal["high", "critical"] = (
                "critical" if min(death.confidence, fact.confidence) >= 0.8 else "high"
            )
            result.append(
                TimelineConflict(
                    code="timeline.dead_character_action",
                    severity=severity,
                    chapter_numbers=[death.chapter_number, fact.chapter_number],
                    event_keys=[death_event.event_key, event.event_key],
                    description=f"{fact.subject} performs a new action after a recorded death.",
                    evidence=[_bounded(death.evidence), _bounded(fact.evidence)],
                    suggested_resolution="Add an explicit resurrection/flashback rule or revise the later action.",
                )
            )
        return result

    def _location_conflicts(
        self, facts: list[AcceptedFactData], events: list[TimelineEventData]
    ) -> list[TimelineConflict]:
        groups: dict[tuple[str, int], list[tuple[AcceptedFactData, TimelineEventData]]] = (
            defaultdict(list)
        )
        for fact, event in zip(facts, events, strict=True):
            if _normalized(fact.predicate) in {_normalized(p) for p in _LOCATION_PREDICATES}:
                groups[(_normalized(fact.subject), fact.chapter_number)].append((fact, event))
        result: list[TimelineConflict] = []
        for group in groups.values():
            locations = {_normalized(fact.object) for fact, _ in group}
            if len(locations) <= 1:
                continue
            confidence = min(fact.confidence for fact, _ in group)
            result.append(
                TimelineConflict(
                    code="timeline.simultaneous_locations",
                    severity="high" if confidence >= 0.8 else "medium",
                    chapter_numbers=sorted({fact.chapter_number for fact, _ in group}),
                    event_keys=[event.event_key for _, event in group],
                    description="A character is recorded in incompatible locations without a transition.",
                    evidence=[_bounded(fact.evidence) for fact, _ in group],
                    suggested_resolution="Add a travel transition or correct one location fact.",
                )
            )
        return result

    def _object_conflicts(
        self, facts: list[AcceptedFactData], events: list[TimelineEventData]
    ) -> list[TimelineConflict]:
        destroyed: dict[str, tuple[AcceptedFactData, TimelineEventData]] = {}
        result: list[TimelineConflict] = []
        for fact, event in zip(facts, events, strict=True):
            predicate = _normalized(fact.predicate)
            value = _normalized(fact.object)
            subject = _normalized(fact.subject)
            if predicate in {"status", "state", "objectstate", "状态"} and value in {
                _normalized(item) for item in _DESTROYED_VALUES
            }:
                destroyed[subject] = (fact, event)
            elif subject in destroyed and predicate in {"used", "uses", "使用"}:
                earlier, earlier_event = destroyed[subject]
                if fact.chapter_number > earlier.chapter_number:
                    result.append(
                        TimelineConflict(
                            code="timeline.destroyed_object_reused",
                            severity="medium",
                            chapter_numbers=[earlier.chapter_number, fact.chapter_number],
                            event_keys=[earlier_event.event_key, event.event_key],
                            description=f"{fact.subject} is used after being destroyed.",
                            evidence=[_bounded(earlier.evidence), _bounded(fact.evidence)],
                            suggested_resolution="Explain a repair/replacement or remove the later use.",
                        )
                    )
        return result

    def _numeric_time_conflicts(self, events: list[TimelineEventData]) -> list[TimelineConflict]:
        timed: list[tuple[int, TimelineEventData]] = []
        for event in events:
            if not event.story_time:
                continue
            match = _TIME_PATTERN.search(event.story_time)
            if match:
                timed.append((int(match.group(1)), event))
        result: list[TimelineConflict] = []
        for (old_value, old), (new_value, new) in pairwise(timed):
            if new_value >= old_value:
                continue
            result.append(
                TimelineConflict(
                    code="timeline.explicit_time_regression",
                    severity="high" if min(old.confidence, new.confidence) >= 0.8 else "medium",
                    chapter_numbers=[old.chapter_number, new.chapter_number],
                    event_keys=[old.event_key, new.event_key],
                    description="An explicit story-time ordinal moves backward without explanation.",
                    evidence=[old.evidence, new.evidence],
                    suggested_resolution="Mark a flashback explicitly or correct the time ordinal.",
                )
            )
        return result

    def _cause_conflicts(
        self, facts: list[AcceptedFactData], events: list[TimelineEventData]
    ) -> list[TimelineConflict]:
        by_subject: dict[str, tuple[AcceptedFactData, TimelineEventData]] = {}
        for fact, event in zip(facts, events, strict=True):
            by_subject.setdefault(_normalized(fact.subject), (fact, event))
        result: list[TimelineConflict] = []
        for fact, event in zip(facts, events, strict=True):
            if _normalized(fact.predicate) not in {"causedby", "原因是", "由导致"}:
                continue
            cause = by_subject.get(_normalized(fact.object))
            if cause is None or cause[0].chapter_number <= fact.chapter_number:
                continue
            result.append(
                TimelineConflict(
                    code="timeline.cause_after_effect",
                    severity="high"
                    if min(cause[0].confidence, fact.confidence) >= 0.8
                    else "medium",
                    chapter_numbers=[fact.chapter_number, cause[0].chapter_number],
                    event_keys=[event.event_key, cause[1].event_key],
                    description="An event is recorded before its stated cause.",
                    evidence=[_bounded(fact.evidence), _bounded(cause[0].evidence)],
                    suggested_resolution="Reorder the events or make retrospective causality explicit.",
                )
            )
        return result

    @staticmethod
    def _deduplicate_conflicts(conflicts: list[TimelineConflict]) -> list[TimelineConflict]:
        unique: dict[tuple[str, tuple[int, ...], tuple[str, ...]], TimelineConflict] = {}
        for conflict in conflicts:
            key = (
                conflict.code,
                tuple(conflict.chapter_numbers),
                tuple(sorted(conflict.event_keys)),
            )
            unique[key] = conflict
        return [unique[key] for key in sorted(unique)]


class CharacterArcAnalyzer:
    """Project accepted facts into character state, knowledge, and relationship histories."""

    def analyze(
        self,
        chapters: list[SnapshotChapter],
        facts: list[AcceptedFactData],
        characters: list[CharacterProfileData],
    ) -> tuple[CharacterArcResult, list[KnowledgeBoundaryData], list[RelationshipPointData]]:
        character_by_name = {_normalized(item.name): item for item in characters}
        facts_by_chapter: dict[int, list[AcceptedFactData]] = defaultdict(list)
        for fact in facts:
            facts_by_chapter[fact.chapter_number].append(fact)
        points: list[CharacterArcPointData] = []
        knowledge: list[KnowledgeBoundaryData] = []
        relationships: list[RelationshipPointData] = []
        issues: list[CharacterArcIssue] = []
        appearances: Counter[int] = Counter()
        last_state: dict[int, str] = {}
        for chapter in chapters:
            chapter_facts = facts_by_chapter[chapter.chapter_number]
            present = {_normalized(name) for name in chapter.characters_present}
            present.update(_normalized(fact.subject) for fact in chapter_facts)
            for normalized_name in sorted(present):
                character = character_by_name.get(normalized_name)
                if character is None:
                    continue
                appearances[character.id] += 1
                related = [
                    fact for fact in chapter_facts if _normalized(fact.subject) == normalized_name
                ]
                state = next(
                    (
                        fact.object
                        for fact in related
                        if _normalized(fact.predicate) in {"state", "status", "状态"}
                    ),
                    last_state.get(character.id, character.current_state),
                )
                previous = last_state.get(character.id)
                if (
                    previous
                    and _normalized(previous) != _normalized(state)
                    and not any(
                        _normalized(fact.predicate) in {"changes", "becomes", "转变", "变为"}
                        for fact in related
                    )
                ):
                    issues.append(
                        CharacterArcIssue(
                            code="character.unexplained_state_shift",
                            severity="medium",
                            character_id=character.id,
                            character_name=character.name,
                            chapter_numbers=[chapter.chapter_number],
                            description="Character state changes without an explicit supporting event.",
                            evidence=[_bounded(fact.evidence) for fact in related[:2]],
                        )
                    )
                last_state[character.id] = state
                locations = [
                    fact.object
                    for fact in related
                    if _normalized(fact.predicate) in {_normalized(p) for p in _LOCATION_PREDICATES}
                ]
                learned = [
                    fact
                    for fact in related
                    if _normalized(fact.predicate)
                    in {_normalized(p) for p in _KNOWLEDGE_PREDICATES}
                ]
                relation_values: dict[str, str] = {}
                for fact in related:
                    relation_type = _RELATIONSHIP_PREDICATES.get(_normalized(fact.predicate))
                    if relation_type is None:
                        continue
                    target = character_by_name.get(_normalized(fact.object))
                    if target is None:
                        continue
                    relation_values[target.name] = relation_type
                    relationships.append(
                        RelationshipPointData(
                            subject_character_id=character.id,
                            object_character_id=target.id,
                            relationship_type=relation_type,  # type: ignore[arg-type]
                            value="active",
                            chapter_number=chapter.chapter_number,
                            chapter_version_id=chapter.chapter_version_id,
                            evidence=_bounded(fact.evidence),
                        )
                    )
                for fact in learned:
                    knowledge.append(
                        KnowledgeBoundaryData(
                            character_id=character.id,
                            character_name=character.name,
                            fact_id=fact.id,
                            learned_chapter=chapter.chapter_number,
                            confidence=fact.confidence,
                        )
                    )
                points.append(
                    CharacterArcPointData(
                        character_id=character.id,
                        character_name=character.name,
                        chapter_number=chapter.chapter_number,
                        chapter_version_id=chapter.chapter_version_id,
                        goals=character.goals,
                        physical_state=state,
                        location=locations[-1] if locations else None,
                        relationships=relation_values,
                        knowledge=[fact.object for fact in learned],
                        decisions=[
                            fact.object
                            for fact in related
                            if _normalized(fact.predicate) in {"decides", "决定"}
                        ],
                        evidence=[_bounded(fact.evidence) for fact in related[:4]],
                    )
                )
        protagonist = next(
            (item for item in characters if _normalized(item.role) in {"protagonist", "主角"}),
            characters[0] if characters else None,
        )
        coverage = (
            appearances[protagonist.id] / max(1, len(chapters)) if protagonist is not None else 0.0
        )
        if protagonist is not None and len(chapters) >= 3 and coverage < 0.5:
            issues.append(
                CharacterArcIssue(
                    code="character.protagonist_absent",
                    severity="high",
                    character_id=protagonist.id,
                    character_name=protagonist.name,
                    chapter_numbers=[item.chapter_number for item in chapters],
                    description="The protagonist is absent from more than half of the book.",
                )
            )
        penalty = sum(
            {"critical": 4, "high": 2, "medium": 0.75, "low": 0.25}[i.severity] for i in issues
        )
        return (
            CharacterArcResult(
                score=_score(penalty),
                points=points,
                issues=issues,
                protagonist_coverage=round(coverage, 4),
            ),
            knowledge,
            relationships,
        )


class ForeshadowingAnalyzer:
    """Compute setup/payoff metrics without inventing implicit semantic matches."""

    def analyze(
        self, items: list[ForeshadowingItemData], *, final_chapter: int
    ) -> ForeshadowingAnalysisResult:
        issues: list[ForeshadowingIssue] = []
        payoff_count = 0
        early = 0
        overdue = 0
        distances: list[int] = []
        for item in items:
            if item.payoff_chapter is not None:
                payoff_count += 1
                distance = item.payoff_chapter - item.setup_chapter
                distances.append(max(0, distance))
                if item.payoff_chapter < item.setup_chapter:
                    early += 1
                    issues.append(
                        ForeshadowingIssue(
                            code="foreshadowing.payoff_before_setup",
                            severity="high",
                            foreshadowing_id=item.id,
                            chapter_numbers=[item.payoff_chapter, item.setup_chapter],
                            description="Payoff occurs before its setup.",
                        )
                    )
            elif item.expected_payoff_chapter <= final_chapter and item.importance.casefold() in {
                "high",
                "critical",
                "重要",
            }:
                overdue += 1
                issues.append(
                    ForeshadowingIssue(
                        code="foreshadowing.major_unresolved",
                        severity="high",
                        foreshadowing_id=item.id,
                        chapter_numbers=[item.setup_chapter, item.expected_payoff_chapter],
                        description="An important planned payoff remains unresolved.",
                    )
                )
        total = len(items)
        rate = payoff_count / total if total else 1.0
        penalty = sum(2.0 for item in issues if item.severity == "high")
        penalty += sum(0.5 for item in issues if item.severity == "medium")
        return ForeshadowingAnalysisResult(
            score=_score(penalty),
            total=total,
            setup_count=total,
            progressed_count=sum(item.status == "open" for item in items),
            payoff_count=payoff_count,
            unresolved_count=total - payoff_count,
            early_payoff_count=early,
            repeated_payoff_count=0,
            overdue_count=overdue,
            no_setup_count=0,
            payoff_rate=round(rate, 4),
            average_setup_payoff_distance=(
                round(sum(distances) / len(distances), 2) if distances else 0
            ),
            issues=issues,
        )


class ChapterTransitionAnalyzer:
    """Assess adjacent accepted versions using explicit metadata and bounded text hints."""

    def analyze(self, chapters: list[SnapshotChapter]) -> list[ChapterTransitionResult]:
        results: list[ChapterTransitionResult] = []
        ordered = sorted(chapters, key=lambda item: item.chapter_number)
        for previous, current in pairwise(ordered):
            issues: list[TransitionIssue] = []
            previous_locations = set(map(_normalized, previous.locations_present))
            current_locations = set(map(_normalized, current.locations_present))
            if (
                previous_locations
                and current_locations
                and previous_locations.isdisjoint(current_locations)
            ):
                text = _normalized(current.content[:300])
                if not any(
                    marker in text
                    for marker in ("travel", "arrive", "journey", "前往", "到达", "路上")
                ):
                    issues.append(
                        TransitionIssue(
                            code="transition.unexplained_location_jump",
                            severity="medium",
                            description="Adjacent chapters change location without a visible transition.",
                            evidence=f"{previous.locations_present} -> {current.locations_present}",
                        )
                    )
            overlap = set(map(_normalized, previous.key_events)) & set(
                map(_normalized, current.key_events)
            )
            if overlap:
                issues.append(
                    TransitionIssue(
                        code="transition.repeated_exposition",
                        severity="low",
                        description="An adjacent chapter repeats a key event description.",
                        evidence=_bounded(next(iter(overlap))),
                    )
                )
            penalty = sum(
                {"critical": 4, "high": 2, "medium": 1, "low": 0.3}[i.severity] for i in issues
            )
            results.append(
                ChapterTransitionResult(
                    from_chapter=previous.chapter_number,
                    to_chapter=current.chapter_number,
                    score=_score(penalty),
                    issues=issues,
                    strengths=[] if issues else ["Adjacent chapter state remains continuous."],
                )
            )
        return results


class PacingAnalyzer:
    """Build explainable per-chapter pacing metrics and global shape warnings."""

    def analyze(self, chapters: list[SnapshotChapter]) -> PacingAnalysisResult:
        ordered = sorted(chapters, key=lambda item: item.chapter_number)
        metrics: list[ChapterPacingMetrics] = []
        for index, chapter in enumerate(ordered):
            normalized = chapter.content.casefold()
            action_hits = sum(
                normalized.count(word) for word in ("冲", "attack", "run", "fight", "追")
            )
            reveal_hits = sum(
                normalized.count(word) for word in ("秘密", "reveal", "discover", "真相")
            )
            hook = 7.0 if chapter.content.rstrip().endswith(("?", "\uff1f", "!", "\uff01")) else 5.5
            action_ratio = min(1.0, action_hits / max(1, chapter.word_count / 80))
            description_ratio = max(0.0, 1.0 - chapter.dialogue_ratio - action_ratio)
            metrics.append(
                ChapterPacingMetrics(
                    chapter_number=chapter.chapter_number,
                    word_count=chapter.word_count,
                    dialogue_ratio=chapter.dialogue_ratio,
                    action_ratio=round(action_ratio, 4),
                    description_ratio=round(description_ratio, 4),
                    conflict_intensity=round(min(10.0, 4.0 + action_ratio * 4), 2),
                    information_reveals=reveal_hits,
                    new_characters=len(chapter.characters_present) if index == 0 else 0,
                    new_locations=len(chapter.locations_present) if index == 0 else 0,
                    foreshadowing_setups=sum("setup" in _normalized(v) for v in chapter.key_events),
                    foreshadowing_payoffs=sum(
                        "payoff" in _normalized(v) for v in chapter.key_events
                    ),
                    chapter_score=chapter.evaluation_score,
                    emotional_intensity=round(min(10.0, 4.0 + chapter.evaluation_score / 3), 2),
                    ending_hook_strength=hook,
                )
            )
        issues: list[PacingIssue] = []
        if len(metrics) >= 5:
            middle = metrics[len(metrics) // 3 : math.ceil(len(metrics) * 2 / 3)]
            outer = [*metrics[: len(metrics) // 3], *metrics[math.ceil(len(metrics) * 2 / 3) :]]
            if (
                middle
                and outer
                and sum(m.chapter_score for m in middle) / len(middle) + 1
                < sum(m.chapter_score for m in outer) / len(outer)
            ):
                issues.append(
                    PacingIssue(
                        code="pacing.middle_slump",
                        severity="medium",
                        chapter_numbers=[item.chapter_number for item in middle],
                        description="The middle section scores materially below the outer acts.",
                    )
                )
        if len(metrics) >= 3 and metrics[-1].word_count < 0.55 * max(
            1, sum(item.word_count for item in metrics[:-1]) / (len(metrics) - 1)
        ):
            issues.append(
                PacingIssue(
                    code="pacing.rushed_ending",
                    severity="high",
                    chapter_numbers=[metrics[-1].chapter_number],
                    description="The ending is much shorter than the preceding chapters.",
                )
            )
        penalty = sum(
            {"critical": 4, "high": 2, "medium": 0.8, "low": 0.25}[i.severity] for i in issues
        )
        return PacingAnalysisResult(score=_score(penalty), chapters=metrics, issues=issues)


class RepetitionDetector:
    """Find exact and high-overlap candidates; never auto-label callbacks as errors."""

    def analyze(self, chapters: list[SnapshotChapter]) -> RepetitionAnalysisResult:
        candidates: list[RepetitionCandidate] = []
        duplicate_paragraphs = 0
        paragraph_owner: dict[str, int] = {}
        for chapter in chapters:
            for paragraph in re.split(r"\n\s*\n", chapter.content):
                normalized = _normalized(paragraph)
                if len(normalized) < 30:
                    continue
                owner = paragraph_owner.get(normalized)
                if owner is not None and owner != chapter.chapter_number:
                    duplicate_paragraphs += 1
                    candidates.append(
                        RepetitionCandidate(
                            code="repetition.exact_paragraph",
                            severity="medium",
                            chapter_numbers=[owner, chapter.chapter_number],
                            similarity=1,
                            evidence=[_bounded(paragraph)],
                        )
                    )
                else:
                    paragraph_owner[normalized] = chapter.chapter_number
        for left, right in combinations(chapters, 2):
            left_grams = self._ngrams(left.content, 3)
            right_grams = self._ngrams(right.content, 3)
            if not left_grams or not right_grams:
                continue
            similarity = len(left_grams & right_grams) / len(left_grams | right_grams)
            if similarity >= 0.55 and not any(
                "callback" in _normalized(event) for event in right.key_events
            ):
                candidates.append(
                    RepetitionCandidate(
                        code="repetition.similar_scene",
                        severity="medium",
                        chapter_numbers=[left.chapter_number, right.chapter_number],
                        similarity=round(similarity, 4),
                        evidence=[left.title, right.title],
                    )
                )
        phrases = Counter(gram for chapter in chapters for gram in self._ngrams(chapter.content, 4))
        repeated_phrases = sum(count >= 4 for count in phrases.values())
        penalty = (
            duplicate_paragraphs * 1.5
            + repeated_phrases * 0.1
            + sum(0.5 for item in candidates if item.code == "repetition.similar_scene")
        )
        return RepetitionAnalysisResult(
            score=_score(penalty),
            candidates=candidates,
            duplicate_paragraphs=duplicate_paragraphs,
            repeated_phrase_count=repeated_phrases,
        )

    @staticmethod
    def _ngrams(content: str, size: int) -> set[str]:
        tokens = re.findall(r"[\w\u3400-\u9fff]+", content.casefold())
        return {" ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1)}
