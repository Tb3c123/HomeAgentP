"""Structured JSON logging with automatic secret redaction."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|api[-_]?key|emby[-_]?token|authorization|cookie|session_id|sid|csrf)",
    re.IGNORECASE,
)

SENSITIVE_VALUE_PATTERNS = [
    re.compile(
        r"((?:password|passwd|secret|token|api_key|apikey|x-api-key|x-emby-token|cookie|session|sid)\s*[=:]\s*\"?)([^\s,;\"'&]+)",
        re.IGNORECASE,
    ),
    re.compile(r"(Bearer\s+)([A-Za-z0-9._~+/=-]+)", re.IGNORECASE),
    re.compile(r"(homeagentp_session=)([^\s;\"']+)", re.IGNORECASE),
    re.compile(r"(SID=)([^\s;\"']+)", re.IGNORECASE),
    re.compile(r"(https?://api\.telegram\.org/bot)([0-9]+:[A-Za-z0-9_-]+)", re.IGNORECASE),
    re.compile(r"\b(bot)([0-9]{5,}:[A-Za-z0-9_-]{20,})\b"),
]


def redact_text(value: str) -> str:
    """Redact inline key=value secrets or bearer tokens from a string."""
    result = value
    for pattern in SENSITIVE_VALUE_PATTERNS:
        result = pattern.sub(r"\1[REDACTED]", result)
    return result


def redact_structure(data: Any) -> Any:
    """Recursively redact sensitive keys and string patterns in dicts and lists."""
    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for k, v in data.items():
            key_str = str(k)
            if SENSITIVE_KEY_PATTERN.search(key_str):
                sanitized[key_str] = "[REDACTED]"
            else:
                sanitized[key_str] = redact_structure(v)
        return sanitized
    if isinstance(data, (list, tuple)):
        return [redact_structure(item) for item in data]
    if isinstance(data, str):
        return redact_text(data)
    return data


class SecretRedactingFilter(logging.Filter):
    """Logging filter that scrubs sensitive strings from log messages and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        record.msg = redact_text(msg)
        record.args = ()
        if hasattr(record, "extra_data"):
            record.extra_data = redact_structure(record.extra_data)
        return True


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON with UTC timestamps and redaction."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        extra_data = getattr(record, "extra_data", None)
        if extra_data is not None:
            payload["context"] = redact_structure(extra_data)
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure and return the HomeAgentP structured logger."""
    logger = logging.getLogger("homeagentp")
    logger.setLevel(level)
    logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.addFilter(SecretRedactingFilter())
    handler.setFormatter(StructuredJsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger
