"""Central consistency rule identifiers, severities, and score penalties."""

from pydantic import Field

from storyforge.enums import ConflictSeverity
from storyforge.schemas.base import RequestModel

CHECKER_VERSION = "m4-consistency-v1"

RULE_FACT_CONTRADICTION = "fact.direct_contradiction"
RULE_DEAD_CHARACTER_ACTION = "character.dead_action"
RULE_LOCATION_CONFLICT = "location.simultaneous"
RULE_KNOWLEDGE_LEAK = "character.knowledge_leak"
RULE_STORY_RULE = "story_rule.structured_violation"
RULE_OBJECT_DESTROYED = "object.destroyed_use"
RULE_OBJECT_POSSESSION = "object.possession_without_transfer"
RULE_FUTURE_FACT = "timeline.future_fact"
RULE_EVENT_ORDER = "timeline.event_order"
RULE_OUTLINE_MISSING = "outline.key_event_missing"
RULE_FORBIDDEN_REVEAL = "outline.forbidden_reveal"
RULE_FORESHADOW_EARLY = "foreshadowing.payoff_before_setup"
RULE_FORESHADOW_REPEAT = "foreshadowing.repeated_payoff"
RULE_FORESHADOW_MISSING = "foreshadowing.planned_payoff_missing"
RULE_FORESHADOW_UNSET = "foreshadowing.payoff_without_setup"


class ConsistencyRuleConfig(RequestModel):
    """Configurable deterministic conflict penalties and confidence floor."""

    version: str = CHECKER_VERSION
    severity_penalties: dict[ConflictSeverity, float] = Field(
        default_factory=lambda: {
            ConflictSeverity.LOW: 0.5,
            ConflictSeverity.MEDIUM: 1.0,
            ConflictSeverity.HIGH: 2.0,
            ConflictSeverity.CRITICAL: 4.0,
        }
    )
    critical_confidence_min: float = Field(default=0.8, ge=0, le=1)
