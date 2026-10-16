"""Safety redline rules (st-safety)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from st_platform.common.types import SafetyVerdictTier

# Alias used by some instructions
RuleSeverity = SafetyVerdictTier


def _coerce_tier(value) -> SafetyVerdictTier:
    if isinstance(value, SafetyVerdictTier):
        return value
    if isinstance(value, str):
        return SafetyVerdictTier(value.strip().upper())
    # tolerate objects exposing .value or name
    if hasattr(value, "value"):
        try:
            return SafetyVerdictTier(str(value.value).strip().upper())
        except ValueError:
            pass
    raise ValueError(f"invalid safety tier: {value!r}")


@runtime_checkable
class RedlineRule(Protocol):
    id: str
    severity: SafetyVerdictTier
    description: str


@dataclass
class RedlineSet:
    """Ordered collection of redline rules."""

    _rules: list[RedlineRule] = field(default_factory=list, repr=False)

    def __init__(self, rules: Iterable[RedlineRule] | None = None) -> None:
        self._rules = []
        for r in (rules or []):
            self.add(r)

    def add(self, rule: RedlineRule) -> None:
        # de-duplicate by id, keep latest position? keep first occurrence order stable
        for i, existing in enumerate(self._rules):
            if getattr(existing, "id", None) == getattr(rule, "id", None):
                self._rules[i] = rule
                return
        self._rules.append(rule)

    def remove(self, rule_or_id) -> None:
        rid = getattr(rule_or_id, "id", rule_or_id)
        self._rules = [r for r in self._rules if getattr(r, "id", None) != rid]

    def ids(self) -> list[str]:
        return [r.id for r in self._rules]

    def __iter__(self):
        return iter(self._rules)

    def __len__(self) -> int:
        return len(self._rules)

    def __contains__(self, item) -> bool:
        rid = getattr(item, "id", item)
        return rid in self.ids()

    def __list__(self):
        return list(self._rules)


def _make_redline(cls_name: str):
    class _Redline:
        id: str
        severity: SafetyVerdictTier
        description: str

        def __init__(
            self,
            id: str,
            severity: SafetyVerdictTier | str | None = None,
            description: str = "",
            severity_level: SafetyVerdictTier | str | None = None,
            **kwargs,
        ) -> None:
            # accept severity_level as alias / primary
            if severity is None and severity_level is not None:
                severity = severity_level
            if severity is None:
                # allow kwargs like level/tier
                for key in ("level", "tier", "severity_tier"):
                    if key in kwargs:
                        severity = kwargs.pop(key)
                        break
            if severity is None:
                severity = SafetyVerdictTier.BLOCK if cls_name == "ComplianceRedline" else SafetyVerdictTier.WARN
            self.id = id
            self.severity = _coerce_tier(severity)
            self.description = description or kwargs.pop("desc", "") or ""
            # compatibility alias (read-only surface)
            self._severity_level = self.severity

        @property
        def severity_level(self) -> SafetyVerdictTier:
            return self.severity

        @severity_level.setter
        def severity_level(self, value) -> None:
            self.severity = _coerce_tier(value)

        def __repr__(self) -> str:
            return f"{cls_name}(id={self.id!r}, severity={self.severity.value!r})"

    _Redline.__name__ = cls_name
    _Redline.__qualname__ = cls_name
    return _Redline


DiagnosticRedline = _make_redline("DiagnosticRedline")
ComplianceRedline = _make_redline("ComplianceRedline")

# Re-bind docstrings for clarity
DiagnosticRedline.__doc__ = "Diagnostic-path redline check."
ComplianceRedline.__doc__ = "Compliance/policy redline check."
