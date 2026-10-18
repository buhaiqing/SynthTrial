"""PHI redaction hook (D-4: medical data never leaves the de-id chain)."""

from __future__ import annotations

import logging
import re
from typing import Any

_PATTERNS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b1[3-9]\d{9}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b\d{15}(\d{2}[0-9Xx])?\b"), "[REDACTED_ID]"),
]


def redact_text(value: str) -> str:
    out = value
    for pat, repl in _PATTERNS:
        out = pat.sub(repl, out)
    return out


def redact(obj: Any) -> Any:
    """Return a redacted deep copy; never raises."""
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        return {k: redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(redact(v) for v in obj)
    return obj


class RedactingFilter(logging.Filter):
    """Logging filter that redacts PHI from record.msg and record.args in place."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact_text(record.msg)
            if record.args:
                if isinstance(record.args, tuple):
                    record.args = tuple(
                        redact(a) if isinstance(a, str) else a for a in record.args
                    )
                elif isinstance(record.args, dict):
                    record.args = {
                        k: (redact(v) if isinstance(v, str) else v)
                        for k, v in record.args.items()
                    }
        except Exception:  # noqa: BLE001, S110 - logging must never raise
            pass
        return True
