"""Conservative fact normalization used only for deterministic comparison."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from storyforge.consistency.models import FactEvidence

_PUNCTUATION_RE = re.compile(
    r"[\s\t\r\n,\uFF0C\u3002.!\uFF01?\uFF1F;\uFF1B:\uFF1A'\""
    r"\u201C\u201D\u2018\u2019\uFF08\uFF09()\[\]{}]+"
)
_NUMBER_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")

BOOLEAN_VALUES = {
    "alive": "alive",
    "surviving": "alive",
    "存活": "alive",
    "活着": "alive",
    "dead": "dead",
    "deceased": "dead",
    "死亡": "dead",
    "已死": "dead",
    "true": "true",
    "yes": "true",
    "是": "true",
    "false": "false",
    "no": "false",
    "否": "false",
}

PREDICATE_ALIASES = {
    "locatedat": "location",
    "isat": "location",
    "location": "location",
    "位于": "location",
    "在": "location",
    "owns": "possession",
    "carries": "possession",
    "possesses": "possession",
    "持有": "possession",
    "携带": "possession",
    "knows": "knowledge",
    "learned": "knowledge",
    "discovered": "knowledge",
    "知道": "knowledge",
    "得知": "knowledge",
    "revealed": "reveal",
    "reveal": "reveal",
    "揭示": "reveal",
    "state": "state",
    "状态": "state",
    "isalive": "alive",
    "alive": "alive",
    "timelineorder": "timeline_order",
    "sequence": "timeline_order",
    "eventstatus": "event_status",
    "uses": "use",
    "used": "use",
    "使用": "use",
    "transfers": "transfer",
    "transferred": "transfer",
    "转移": "transfer",
    "moves": "move",
    "travels": "move",
    "arrives": "arrive",
    "departs": "depart",
    "walks": "walk",
    "speaks": "speak",
    "attacks": "attack",
}


@dataclass(frozen=True, slots=True)
class NormalizedFact:
    """Comparison-only normalized values with original evidence retained."""

    subject: str
    predicate: str
    object: str
    raw: FactEvidence


class FactNormalizer:
    """Normalize exact aliases without fuzzy semantic matching."""

    def normalize_subject(self, value: str) -> str:
        """Normalize case, whitespace, and common punctuation in a subject."""
        return _PUNCTUATION_RE.sub("", value.casefold()).strip()

    def normalize_predicate(self, value: str) -> str:
        """Normalize known predicate aliases, preserving unknown predicates."""
        normalized = self.normalize_subject(value).replace("_", "")
        return PREDICATE_ALIASES.get(normalized, normalized)

    def normalize_object(self, value: str) -> str:
        """Normalize booleans, numbers, case, whitespace, and punctuation."""
        numeric_candidate = re.sub(r"\s+", "", value.casefold())
        if _NUMBER_RE.fullmatch(numeric_candidate):
            try:
                number = Decimal(numeric_candidate).normalize()
            except InvalidOperation:
                number = None
            if number is not None:
                normalized_number = format(number, "f")
                if "." in normalized_number:
                    normalized_number = normalized_number.rstrip("0").rstrip(".")
                return normalized_number or "0"
        normalized = self.normalize_subject(value)
        boolean = BOOLEAN_VALUES.get(normalized)
        if boolean is not None:
            return boolean
        return normalized

    def normalize(self, fact: FactEvidence) -> NormalizedFact:
        """Return normalized comparison values while retaining the raw fact."""
        return NormalizedFact(
            subject=self.normalize_subject(fact.subject),
            predicate=self.normalize_predicate(fact.predicate),
            object=self.normalize_object(fact.object),
            raw=fact,
        )

    def identity_hash(self, subject: str, predicate: str, object_value: str) -> str:
        """Return a stable exact-normalized identity for persistence idempotency."""
        payload = "\x1f".join(
            (
                self.normalize_subject(subject),
                self.normalize_predicate(predicate),
                self.normalize_object(object_value),
            )
        )
        return sha256(payload.encode("utf-8")).hexdigest()
