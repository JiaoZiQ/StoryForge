"""Conservative graph identity normalization."""

import re
import unicodedata

_PUNCTUATION = re.compile(
    r"[\s\-\u2014_.,\uff0c\u3002:\uff1a;\uff1b!?\uff01\uff1f'\""
    r"\u201c\u201d\u2018\u2019\uff08\uff09()\u3010\u3011\[\]]+"
)


class GraphEntityNormalizer:
    """Normalize explicit names without fuzzy or semantic merging."""

    def normalize(self, name: str) -> str:
        normalized = unicodedata.normalize("NFKC", name).casefold().strip()
        return _PUNCTUATION.sub("", normalized)

    def disambiguation_key(self, *, entity_type: str, description: str | None) -> str:
        """Use only explicit structured type information to separate same-name nodes."""
        if not description:
            return ""
        marker = re.search(r"\b(?:id|role|type)\s*[:=]\s*([\w-]+)", description.casefold())
        return f"{entity_type}:{marker.group(1)}" if marker else ""
