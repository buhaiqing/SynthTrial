from st_platform.common.types import SafetyVerdictTier
from st_platform.safety.checker import SafetyChecker, SafetyVerdict
from st_platform.safety.coverage import CoverageReport
from st_platform.safety.rules import (
    ComplianceRedline,
    DiagnosticRedline,
    RedlineRule,
    RedlineSet,
    RuleSeverity,
)


def test_rules_protocol_and_set():
    r1 = DiagnosticRedline(id="r1", severity=SafetyVerdictTier.BLOCK, description="d")
    r2 = ComplianceRedline(id="r2", severity_level="WARN", description="w")
    assert isinstance(r1, RedlineRule)
    assert r2.severity == SafetyVerdictTier.WARN
    assert r2.severity_level == SafetyVerdictTier.WARN
    s = RedlineSet()
    s.add(r1)
    s.add(r2)
    assert s.ids() == ["r1", "r2"]
    s.remove("r1")
    assert s.ids() == ["r2"]
    assert len(s) == 1


def test_checker_block_cannot_be_overridden():
    rules = [
        DiagnosticRedline(id="rl.block", severity=SafetyVerdictTier.BLOCK, description="block"),
        DiagnosticRedline(id="rl.warn", severity=SafetyVerdictTier.WARN, description="warn"),
    ]
    checker = SafetyChecker(rules)
    cov = CoverageReport(registered=rules, evaluated=rules)
    verdict = checker.check(
        results_by_rule={"rl.block": True, "rl.warn": False},
        coverage=cov,
    )
    assert isinstance(verdict, SafetyVerdict)
    assert verdict.tier == SafetyVerdictTier.BLOCK
    assert "rl.block" in verdict.blocking_ids
    # even if someone tries to pass all metrics, block remains (simulated by re-check)
    verdict2 = checker.check(
        {"rl.block": True},
        cov,
    )
    assert verdict2.tier == SafetyVerdictTier.BLOCK


def test_checker_pass_and_warn():
    rules = [
        DiagnosticRedline(id="rl.warn", severity="WARN", description="w"),
    ]
    checker = SafetyChecker(rules)
    cov = CoverageReport(registered=rules, evaluated=rules)
    v = checker.check(results_by_rule={"rl.warn": False}, coverage=cov)
    assert v.tier == SafetyVerdictTier.PASS
    v2 = checker.check(results_by_rule={"rl.warn": True}, coverage=cov)
    assert v2.tier == SafetyVerdictTier.WARN
    assert v2.warning_ids == ["rl.warn"]


def test_checker_counts_from_coverage():
    rules = [DiagnosticRedline(id=f"r{i}", severity="BLOCK", description="") for i in range(3)]
    checker = SafetyChecker(rules)
    cov = CoverageReport(registered=rules, evaluated=[rules[0], rules[1]])
    v = checker.check(results_by_rule={}, coverage=cov)
    assert v.covered_rule_count == 2
    assert v.uncovered_rule_count == 1
    assert v.uncovered_ratio == 1 / 3


def test_rule_severity_alias():
    assert RuleSeverity.BLOCK == SafetyVerdictTier.BLOCK
