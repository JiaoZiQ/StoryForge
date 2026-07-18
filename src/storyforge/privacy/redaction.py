"""Conservative secret redaction for logs, audit summaries, and strict egress."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from storyforge.privacy.models import RedactionSummary

_PATTERNS = {
    "authorization": re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+"),
    "api_key": re.compile(
        r"(?i)(?:(?:api[_-]?key|token|secret)\s*[:=]\s*)?(?:sk-[A-Za-z0-9_-]{12,})"
    ),
    "database_url": re.compile(r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^:\s/@]+:)([^@\s/]+)(@)"),
}


class RedactionService:
    """Replace only high-confidence secret patterns and report category counts."""

    def redact(
        self,
        value: str,
        *,
        redact_email: bool = False,
        redact_phone: bool = False,
        custom_terms: Iterable[str] = (),
    ) -> tuple[str, RedactionSummary]:
        counts: Counter[str] = Counter()
        rendered = value
        for category, pattern in _PATTERNS.items():
            if category == "database_url":
                rendered, amount = pattern.subn(r"\1[REDACTED]\3", rendered)
            elif category == "authorization":
                rendered, amount = pattern.subn(r"\1[REDACTED]", rendered)
            else:
                rendered, amount = pattern.subn("[REDACTED]", rendered)
            counts[category] += amount
        if redact_email:
            rendered, amount = re.subn(
                r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])",
                "[REDACTED]",
                rendered,
            )
            counts["email"] += amount
        if redact_phone:
            rendered, amount = re.subn(
                r"(?<!\d)(?:\+?\d[\d -]{7,}\d)(?!\d)", "[REDACTED]", rendered
            )
            counts["phone"] += amount
        for term in sorted({item for item in custom_terms if item}, key=len, reverse=True):
            amount = rendered.count(term)
            if amount:
                rendered = rendered.replace(term, "[REDACTED]")
                counts["custom"] += amount
        return rendered, RedactionSummary(categories={k: v for k, v in counts.items() if v})
