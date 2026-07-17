"""Container-friendly logging with deterministic sensitive-value redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from storyforge.settings import Settings

_SENSITIVE_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[^\s,;]+"),
    re.compile(r"(?i)\b(authorization|cookie|api[_-]?key|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)(postgres(?:ql)?(?:\+psycopg)?://[^:/\s]+:)[^@\s]+(@)"),
)
_STRUCTURED_FIELDS = (
    "request_id",
    "method",
    "path",
    "status",
    "duration_ms",
    "workflow_run_id",
)


def redact_sensitive(value: str) -> str:
    """Remove common credential forms without exposing the original value."""
    result = value
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.groups == 2:
            result = pattern.sub(r"\1[REDACTED]\2", result)
        else:
            result = pattern.sub("[REDACTED]", result)
    return result


class SensitiveDataFilter(logging.Filter):
    """Redact the rendered message before any formatter emits it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive(record.getMessage())
        record.args = ()
        return True


class JsonLogFormatter(logging.Formatter):
    """Emit one compact JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive(record.getMessage()),
        }
        for name in _STRUCTURED_FIELDS:
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(settings: Settings, *, force: bool = False) -> None:
    """Configure stdout logging for local text or production JSON output."""
    root = logging.getLogger()
    if root.handlers and not force:
        root.setLevel(getattr(logging, settings.log_level))
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(SensitiveDataFilter())
    if settings.log_format == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level))
