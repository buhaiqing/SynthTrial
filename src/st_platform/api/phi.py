"""PHI redaction hook (D-4: medical data never leaves the de-id chain)."""

from __future__ import annotations

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