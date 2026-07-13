"""Explainable deterministic consistency rules for generated chapters."""

from collections import defaultdict

from storyforge.consistency.models import (
    ConsistencyCheckRequest,
    ConsistencyCheckResult,
    ConsistencyConflict,
    FactEvidence,
)
from storyforge.consistency.normalizer import FactNormalizer, NormalizedFact
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
    ConsistencyRuleConfig,
)
from storyforge.enums import ConflictSeverity, ConflictType, ForeshadowingStatus
from storyforge.evaluation.scoring import bounded_score

_ACTION_PREDICATES = {"walk", "speak", "attack", "arrive", "move", "use"}
_TRANSITION_PREDICATES = {"move", "arrive", "depart", "transfer"}
_MEMORY_FACT_TYPES = {"memory", "dream", "quotation", "corpse", "flashback"}


class ConsistencyChecker:
    """Compare current evidence with prior canonical state using ten rule groups."""

    checked_rule_count = 10

    def __init__(
        self,
        normalizer: FactNormalizer | None = None,
        config: ConsistencyRuleConfig | None = None,
    ) -> None:
        self.normalizer = normalizer or FactNormalizer()
        self.config = config or ConsistencyRuleConfig()

    def check(self, request: ConsistencyCheckRequest) -> ConsistencyCheckResult:
        """Run all rule groups and return an auditable bounded result."""
        new = [self.normalizer.normalize(item) for item in request.new_facts]
        history = [self.normalizer.normalize(item) for item in request.historical_facts]
        conflicts = [
            *self._direct_fact_conflicts(request, new, history),
            *self._dead_character_actions(request, new, history),
            *self._location_conflicts(request, new),
            *self._knowledge_leaks(request, new, history),
            *self._story_rule_conflicts(request, new),
            *self._object_state_conflicts(request, new, history),
            *self._timeline_conflicts(request, new, history),
            *self._outline_conflicts(request, new),
            *self._forbidden_reveals(request, new),
            *self._foreshadowing_conflicts(request),
        ]
        conflicts = self._deduplicate(conflicts)
        counts = CounterBySeverity(conflicts)
        penalty = sum(self.config.severity_penalties[item.severity] for item in conflicts)
        return ConsistencyCheckResult(
            score=bounded_score(10 - penalty),
            conflicts=conflicts,
            checked_rule_count=self.checked_rule_count,
            critical_count=counts.critical,
            high_count=counts.high,
            medium_count=counts.medium,
            low_count=counts.low,
            checker_version=self.config.version,
        )

    def _conflict(
        self,
        request: ConsistencyCheckRequest,
        *,
        conflict_type: ConflictType,
        severity: ConflictSeverity,
        subject: str,
        description: str,
        new_evidence: str,
        rule_code: str,
        confidence: float,
        suggested_resolution: str,
        existing: FactEvidence | None = None,
    ) -> ConsistencyConflict:
        if (
            severity is ConflictSeverity.CRITICAL
            and confidence < self.config.critical_confidence_min
        ):
            severity = ConflictSeverity.HIGH
        return ConsistencyConflict(
            conflict_type=conflict_type,
            severity=severity,
            subject=subject,
            description=description,
            new_evidence=new_evidence,
            existing_evidence=existing.source_quote or str(existing.model_dump())
            if existing
            else None,
            existing_fact_id=existing.fact_id if existing else None,
            chapter_number=request.chapter_number,
            suggested_resolution=suggested_resolution,
            confidence=confidence,
            rule_code=rule_code,
        )

    def _direct_fact_conflicts(
        self,
        request: ConsistencyCheckRequest,
        new: list[NormalizedFact],
        history: list[NormalizedFact],
    ) -> list[ConsistencyConflict]:
        conflicts = []
        for current in new:
            for existing in history:
                if (
                    current.subject == existing.subject
                    and current.predicate == existing.predicate
                    and current.object != existing.object
                ):
                    confidence = min(current.raw.confidence, existing.raw.confidence)
                    conflicts.append(
                        self._conflict(
                            request,
                            conflict_type=ConflictType.FACT_CONTRADICTION,
                            severity=ConflictSeverity.HIGH,
                            subject=current.raw.subject,
                            description="A new fact directly contradicts an earlier fact.",
                            new_evidence=current.raw.source_quote or str(current.raw.model_dump()),
                            existing=existing.raw,
                            confidence=confidence,
                            rule_code=RULE_FACT_CONTRADICTION,
                            suggested_resolution="Verify which fact is canonical and update the chapter.",
                        )
                    )
        return conflicts

    def _dead_character_actions(
        self,
        request: ConsistencyCheckRequest,
        new: list[NormalizedFact],
        history: list[NormalizedFact],
    ) -> list[ConsistencyConflict]:
        dead = {
            item.subject
            for item in history
            if item.predicate in {"alive", "state"} and item.object == "dead"
        }
        dead.update(
            self.normalizer.normalize_subject(item.character_name)
            for item in request.character_updates
            if self.normalizer.normalize_object(item.value) == "dead"
        )
        for character in request.characters:
            state = self.normalizer.normalize_object(character.current_state)
            if (
                "dead" in state
                or "死亡" in character.current_state
                or "已死" in character.current_state
            ):
                dead.add(self.normalizer.normalize_subject(character.name))
        resurrection_allowed = any(
            bool(rule.structured_metadata.get("allows_resurrection"))
            for rule in request.story_rules
        )
        if resurrection_allowed:
            return []
        conflicts = []
        for item in new:
            if (
                item.subject in dead
                and item.predicate in _ACTION_PREDICATES
                and item.raw.fact_type.casefold() not in _MEMORY_FACT_TYPES
                and item.predicate != "corpse_moved"
            ):
                conflicts.append(
                    self._conflict(
                        request,
                        conflict_type=ConflictType.CHARACTER_STATE,
                        severity=ConflictSeverity.CRITICAL,
                        subject=item.raw.subject,
                        description="A character marked dead performs a new action.",
                        new_evidence=item.raw.source_quote or str(item.raw.model_dump()),
                        confidence=item.raw.confidence,
                        rule_code=RULE_DEAD_CHARACTER_ACTION,
                        suggested_resolution="Mark the scene as memory/dream or establish resurrection.",
                    )
                )
        return conflicts

    def _location_conflicts(
        self, request: ConsistencyCheckRequest, new: list[NormalizedFact]
    ) -> list[ConsistencyConflict]:
        if any(item.predicate in _TRANSITION_PREDICATES for item in new):
            return []
        locations: dict[str, list[NormalizedFact]] = defaultdict(list)
        for item in new:
            if item.predicate == "location":
                locations[item.subject].append(item)
        conflicts = []
        for items in locations.values():
            if len({item.object for item in items}) > 1:
                conflicts.append(
                    self._conflict(
                        request,
                        conflict_type=ConflictType.LOCATION,
                        severity=ConflictSeverity.HIGH,
                        subject=items[0].raw.subject,
                        description="A character is placed in incompatible locations without movement.",
                        new_evidence="; ".join(
                            item.raw.source_quote or item.raw.object for item in items
                        ),
                        confidence=min(item.raw.confidence for item in items),
                        rule_code=RULE_LOCATION_CONFLICT,
                        suggested_resolution="Add a movement transition or correct one location fact.",
                    )
                )
        return conflicts

    def _knowledge_leaks(
        self,
        request: ConsistencyCheckRequest,
        new: list[NormalizedFact],
        history: list[NormalizedFact],
    ) -> list[ConsistencyConflict]:
        characters = {
            self.normalizer.normalize_subject(item.name): item for item in request.characters
        }
        all_secrets = {
            self.normalizer.normalize_object(secret)
            for item in request.characters
            for secret in item.secrets
        }
        conflicts = []
        for item in new:
            if item.predicate != "knowledge" or item.object not in all_secrets:
                continue
            character = characters.get(item.subject)
            known = (
                {self.normalizer.normalize_object(value) for value in character.knowledge}
                if character
                else set()
            )
            acquired = any(
                previous.subject == item.subject
                and previous.object == item.object
                and previous.predicate in {"knowledge", "reveal"}
                for previous in history
            )
            if item.object not in known and not acquired:
                conflicts.append(
                    self._conflict(
                        request,
                        conflict_type=ConflictType.CHARACTER_KNOWLEDGE,
                        severity=ConflictSeverity.HIGH,
                        subject=item.raw.subject,
                        description="A character knows an unrevealed secret without an acquisition event.",
                        new_evidence=item.raw.source_quote or item.raw.object,
                        confidence=item.raw.confidence,
                        rule_code=RULE_KNOWLEDGE_LEAK,
                        suggested_resolution="Add a reveal/learning event or remove the knowledge.",
                    )
                )
        return conflicts

    def _story_rule_conflicts(
        self, request: ConsistencyCheckRequest, new: list[NormalizedFact]
    ) -> list[ConsistencyConflict]:
        current_locations = {item.object for item in new if item.predicate == "location"}
        conflicts = []
        for rule in request.story_rules:
            configured_predicates = rule.structured_metadata.get("forbidden_predicates", [])
            if not isinstance(configured_predicates, list):
                configured_predicates = []
            forbidden = {
                self.normalizer.normalize_predicate(str(value)) for value in configured_predicates
            }
            location_value = rule.structured_metadata.get("location")
            location = (
                self.normalizer.normalize_object(str(location_value))
                if location_value is not None
                else None
            )
            for item in new:
                if item.predicate in forbidden and (
                    location is None or location in current_locations
                ):
                    conflicts.append(
                        self._conflict(
                            request,
                            conflict_type=ConflictType.STORY_RULE,
                            severity=ConflictSeverity.HIGH,
                            subject=item.raw.subject,
                            description=f"A structured story rule is violated: {rule.statement}",
                            new_evidence=item.raw.source_quote or item.raw.object,
                            confidence=item.raw.confidence,
                            rule_code=RULE_STORY_RULE,
                            suggested_resolution="Revise the action or explicitly change the story rule.",
                        )
                    )
        return conflicts

    def _object_state_conflicts(
        self,
        request: ConsistencyCheckRequest,
        new: list[NormalizedFact],
        history: list[NormalizedFact],
    ) -> list[ConsistencyConflict]:
        conflicts = []
        destroyed = {
            item.subject: item
            for item in history
            if item.predicate == "state" and item.object in {"destroyed", "销毁", "损毁"}
        }
        for item in new:
            target = item.object if item.predicate in {"use", "possession"} else item.subject
            existing = destroyed.get(target)
            if existing is not None and item.predicate in {"use", "possession"}:
                conflicts.append(
                    self._conflict(
                        request,
                        conflict_type=ConflictType.OBJECT_STATE,
                        severity=ConflictSeverity.HIGH,
                        subject=item.raw.object,
                        description="An object previously destroyed is used or possessed again.",
                        new_evidence=item.raw.source_quote or item.raw.object,
                        existing=existing.raw,
                        confidence=min(item.raw.confidence, existing.raw.confidence),
                        rule_code=RULE_OBJECT_DESTROYED,
                        suggested_resolution="Establish repair/replacement or use a different object.",
                    )
                )
        if not any(item.predicate == "transfer" for item in new):
            old_holders = {item.object: item for item in history if item.predicate == "possession"}
            for item in new:
                existing = old_holders.get(item.object)
                if (
                    existing is not None
                    and item.predicate == "possession"
                    and existing.subject != item.subject
                ):
                    conflicts.append(
                        self._conflict(
                            request,
                            conflict_type=ConflictType.OBJECT_STATE,
                            severity=ConflictSeverity.MEDIUM,
                            subject=item.raw.object,
                            description="Possession changes owner without a transfer event.",
                            new_evidence=item.raw.source_quote or item.raw.subject,
                            existing=existing.raw,
                            confidence=min(item.raw.confidence, existing.raw.confidence),
                            rule_code=RULE_OBJECT_POSSESSION,
                            suggested_resolution="Add a transfer event or correct the owner.",
                        )
                    )
        return conflicts

    def _timeline_conflicts(
        self,
        request: ConsistencyCheckRequest,
        new: list[NormalizedFact],
        history: list[NormalizedFact],
    ) -> list[ConsistencyConflict]:
        conflicts = []
        for item in (*new, *history):
            if item.raw.valid_from_chapter > request.chapter_number:
                conflicts.append(
                    self._conflict(
                        request,
                        conflict_type=ConflictType.TIMELINE,
                        severity=ConflictSeverity.HIGH,
                        subject=item.raw.subject,
                        description="A fact from a future validity interval is used now.",
                        new_evidence=item.raw.source_quote or item.raw.object,
                        existing=item.raw if item in history else None,
                        confidence=item.raw.confidence,
                        rule_code=RULE_FUTURE_FACT,
                        suggested_resolution="Exclude future facts from the current chapter context.",
                    )
                )
        history_status = {
            item.subject: item for item in history if item.predicate == "event_status"
        }
        history_order = {
            item.subject: item for item in history if item.predicate == "timeline_order"
        }
        for item in new:
            existing = history_status.get(item.subject)
            if (
                existing
                and existing.object == "ended"
                and item.predicate == "event_status"
                and item.object in {"notstarted", "尚未开始"}
            ):
                conflicts.append(
                    self._conflict(
                        request,
                        conflict_type=ConflictType.TIMELINE,
                        severity=ConflictSeverity.HIGH,
                        subject=item.raw.subject,
                        description="An ended event is marked as not started.",
                        new_evidence=item.raw.source_quote or item.raw.object,
                        existing=existing.raw,
                        confidence=min(item.raw.confidence, existing.raw.confidence),
                        rule_code=RULE_EVENT_ORDER,
                        suggested_resolution="Correct the event status chronology.",
                    )
                )
            previous_order = history_order.get(item.subject)
            if previous_order and item.predicate == "timeline_order":
                try:
                    backwards = float(item.object) < float(previous_order.object)
                except ValueError:
                    backwards = False
                if backwards:
                    conflicts.append(
                        self._conflict(
                            request,
                            conflict_type=ConflictType.TIMELINE,
                            severity=ConflictSeverity.MEDIUM,
                            subject=item.raw.subject,
                            description="An explicit timeline sequence moves backwards.",
                            new_evidence=item.raw.source_quote or item.raw.object,
                            existing=previous_order.raw,
                            confidence=min(item.raw.confidence, previous_order.raw.confidence),
                            rule_code=RULE_EVENT_ORDER,
                            suggested_resolution="Restore monotonic event order.",
                        )
                    )
        return conflicts

    def _outline_conflicts(
        self, request: ConsistencyCheckRequest, new: list[NormalizedFact]
    ) -> list[ConsistencyConflict]:
        searchable = self.normalizer.normalize_object(
            request.content
            + " "
            + " ".join(f"{item.raw.subject}{item.raw.predicate}{item.raw.object}" for item in new)
        )
        return [
            self._conflict(
                request,
                conflict_type=ConflictType.OUTLINE_VIOLATION,
                severity=ConflictSeverity.MEDIUM,
                subject=event,
                description="A planned key event is not evidenced in the chapter.",
                new_evidence="No matching content or fact evidence.",
                confidence=1,
                rule_code=RULE_OUTLINE_MISSING,
                suggested_resolution="Add the planned event or update the chapter outline.",
            )
            for event in request.outline.key_events
            if self.normalizer.normalize_object(event) not in searchable
        ]

    def _forbidden_reveals(
        self, request: ConsistencyCheckRequest, new: list[NormalizedFact]
    ) -> list[ConsistencyConflict]:
        searchable = self.normalizer.normalize_object(
            request.content + " " + " ".join(item.raw.object for item in new)
        )
        return [
            self._conflict(
                request,
                conflict_type=ConflictType.OUTLINE_VIOLATION,
                severity=ConflictSeverity.HIGH,
                subject=reveal,
                description="The chapter exposes content explicitly forbidden by its outline.",
                new_evidence=reveal,
                confidence=1,
                rule_code=RULE_FORBIDDEN_REVEAL,
                suggested_resolution="Remove or defer the forbidden reveal.",
            )
            for reveal in request.outline.forbidden_reveals
            if self.normalizer.normalize_object(reveal) in searchable
        ]

    def _foreshadowing_conflicts(
        self, request: ConsistencyCheckRequest
    ) -> list[ConsistencyConflict]:
        conflicts = []
        records = {item.foreshadowing_id: item for item in request.active_foreshadowing}
        resolved_descriptions = {
            self.normalizer.normalize_object(item.description)
            for item in request.active_foreshadowing
            if item.status is ForeshadowingStatus.RESOLVED
            and (item.payoff_chapter is None or item.payoff_chapter < request.chapter_number)
        }
        resolved_now = {
            item.foreshadowing_id
            for item in request.foreshadowing_updates
            if item.action == "resolve" and item.foreshadowing_id is not None
        }
        for item in request.active_foreshadowing:
            if item.payoff_chapter is not None and item.payoff_chapter < item.setup_chapter:
                conflicts.append(
                    self._conflict(
                        request,
                        conflict_type=ConflictType.FORESHADOWING,
                        severity=ConflictSeverity.HIGH,
                        subject=item.description,
                        description="Foreshadowing payoff occurs before setup.",
                        new_evidence=str(item.payoff_chapter),
                        confidence=1,
                        rule_code=RULE_FORESHADOW_EARLY,
                        suggested_resolution="Move payoff after setup.",
                    )
                )
        for planned in request.outline.payoff_foreshadowing:
            normalized = self.normalizer.normalize_object(planned)
            if normalized in resolved_descriptions:
                conflicts.append(
                    self._conflict(
                        request,
                        conflict_type=ConflictType.FORESHADOWING,
                        severity=ConflictSeverity.MEDIUM,
                        subject=planned,
                        description="An already resolved foreshadowing is paid off again.",
                        new_evidence=planned,
                        confidence=1,
                        rule_code=RULE_FORESHADOW_REPEAT,
                        suggested_resolution="Remove the duplicate payoff.",
                    )
                )
            matching = [
                item
                for item in request.active_foreshadowing
                if normalized in self.normalizer.normalize_object(item.description)
            ]
            if matching and not any(
                item.foreshadowing_id in resolved_now or item.status is ForeshadowingStatus.RESOLVED
                for item in matching
            ):
                conflicts.append(
                    self._conflict(
                        request,
                        conflict_type=ConflictType.FORESHADOWING,
                        severity=ConflictSeverity.MEDIUM,
                        subject=planned,
                        description="A planned payoff has no resolution update.",
                        new_evidence=planned,
                        confidence=1,
                        rule_code=RULE_FORESHADOW_MISSING,
                        suggested_resolution="Add the payoff event or update the plan.",
                    )
                )
        for update in request.foreshadowing_updates:
            if update.action == "resolve" and (
                update.foreshadowing_id is None or update.foreshadowing_id not in records
            ):
                conflicts.append(
                    self._conflict(
                        request,
                        conflict_type=ConflictType.FORESHADOWING,
                        severity=ConflictSeverity.HIGH,
                        subject=update.description,
                        description="A payoff references foreshadowing that was never set up.",
                        new_evidence=update.description,
                        confidence=update.confidence,
                        rule_code=RULE_FORESHADOW_UNSET,
                        suggested_resolution="Add a prior setup or remove the payoff.",
                    )
                )
        return conflicts

    @staticmethod
    def _deduplicate(conflicts: list[ConsistencyConflict]) -> list[ConsistencyConflict]:
        seen: set[tuple[str, str, str]] = set()
        result = []
        for item in conflicts:
            key = (item.rule_code, item.subject.casefold(), item.description)
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result


class CounterBySeverity:
    """Small typed severity counter without a dynamic dictionary interface."""

    def __init__(self, conflicts: list[ConsistencyConflict]) -> None:
        self.critical = sum(item.severity is ConflictSeverity.CRITICAL for item in conflicts)
        self.high = sum(item.severity is ConflictSeverity.HIGH for item in conflicts)
        self.medium = sum(item.severity is ConflictSeverity.MEDIUM for item in conflicts)
        self.low = sum(item.severity is ConflictSeverity.LOW for item in conflicts)
