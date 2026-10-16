"""SafetyChecker: applies redlines to produce a 3-tier verdict (st-safety)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from st_platform.common.types import SafetyVerdictTier
from st_platform.safety.coverage import CoverageReport
from st_platform.safety.rules import RedlineSet


@dataclass
class SafetyVerdict:
    tier: SafetyVerdictTier
    blocking_ids: list[str] = field(default_factory=list)
    warning_ids: list[str] = field(default_factory=list)
    covered_rule_count: int = 0
    uncovered_rule_count: int = 0
    uncovered_ratio: float = 0.0
    # informational extras
    passing_ids: list[str] = field(default_factory=list)
    fired_ids: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


class SafetyChecker:
    def __init__(self, redlines: Any = None, rules: Any = None, **kwargs) -> None:
        src = redlines if redlines is not None else rules
        if src is None:
            src = kwargs.get("redlines") or kwargs.get("rules") or []
        if isinstance(src, RedlineSet):
            self.redlines = src
        elif isinstance(src, (list, tuple, set)):
            self.redlines = RedlineSet(src)
        else:
            # maybe iterable of rules or a single coverage? be lenient
            try:
                self.redlines = RedlineSet(list(src))
            except (ValueError, TypeError, AttributeError):
                self.redlines = RedlineSet()
        self._severity_cache = None

    @property
    def rule_ids(self) -> list[str]:
        return self.redlines.ids()

    def _rule_map(self) -> dict[str, Any]:
        return {r.id: r for r in self.redlines}

    def _severity_of(self, rule_id: str):
        r = self._rule_map().get(rule_id)
        if r is None:
            return None
        sev = getattr(r, "severity", None)
        if sev is None:
            sev = getattr(r, "severity_level", None)
        if isinstance(sev, str):
            sev = SafetyVerdictTier(sev.strip().upper())
        return sev

    def check(self, *args, **kwargs) -> SafetyVerdict:
        # resolve results_by_rule
        results_by_rule = kwargs.get("results_by_rule")
        if results_by_rule is None:
            results_by_rule = kwargs.get("results")
        if results_by_rule is None and len(args) >= 1 and isinstance(args[0], dict):
            results_by_rule = args[0]
        if results_by_rule is None:
            results_by_rule = {}
        results_by_rule = dict(results_by_rule)

        # resolve coverage
        coverage = kwargs.get("coverage")
        if coverage is None:
            coverage = kwargs.get("coverage_report")
        # positional second arg could be coverage
        if coverage is None and len(args) >= 2 and not isinstance(args[1], dict):
            coverage = args[1]
        if coverage is None:
            # try construct from kwargs counts
            rc = kwargs.get("registered_count")
            ec = kwargs.get("evaluated_count")
            if rc is not None or ec is not None:
                # best-effort: build coverage with counts only is not id-based;
                # fall back to None and compute from rules/results below
                pass

        rule_map = self._rule_map()
        # Build coverage object if not provided
        if coverage is None:
            registered_ids = set(rule_map.keys())
            evaluated_ids = set(results_by_rule.keys())
            coverage = CoverageReport(registered=registered_ids, evaluated=evaluated_ids)
        elif not isinstance(coverage, CoverageReport):
            try:
                coverage = CoverageReport(registered=getattr(coverage, "registered_rule_ids", None) or [],
                                           evaluated=getattr(coverage, "evaluated_rule_ids", None) or [])
            except (ValueError, TypeError, AttributeError):
                coverage = CoverageReport(registered=set(rule_map.keys()), evaluated=set(results_by_rule.keys()))

        # Determine fired rules (value True means rule fired / violated)
        fired: list[str] = []
        for rid, val in results_by_rule.items():
            if bool(val):
                fired.append(str(rid))

        blocking_ids = []
        warning_ids = []
        passing_fired = []
        for rid in fired:
            sev = self._severity_of(rid)
            if sev == SafetyVerdictTier.BLOCK:
                blocking_ids.append(rid)
            elif sev == SafetyVerdictTier.WARN:
                warning_ids.append(rid)
            else:
                passing_fired.append(rid)

        # guardrail-before-effect: any BLOCK fired => BLOCK regardless
        if blocking_ids:
            tier = SafetyVerdictTier.BLOCK
        elif warning_ids:
            tier = SafetyVerdictTier.WARN
        else:
            tier = SafetyVerdictTier.PASS

        verdict = SafetyVerdict(
            tier=tier,
            blocking_ids=blocking_ids,
            warning_ids=warning_ids,
            covered_rule_count=coverage.covered_rule_count,
            uncovered_rule_count=coverage.uncovered_rule_count,
            uncovered_ratio=coverage.uncovered_ratio,
            passing_ids=passing_fired,
            fired_ids=fired,
            evidence=dict(results_by_rule),
        )
        return verdict
