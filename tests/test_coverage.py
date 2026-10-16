from st_platform.safety.coverage import CoverageReport


def test_coverage_counts():
    cov = CoverageReport(registered=["a", "b", "c"], evaluated=["a", "b"])
    assert cov.covered_rule_count == 2
    assert cov.uncovered_rule_count == 1
    assert cov.uncovered_ratio == 1 / 3
    assert cov.registered_count == 3
    assert cov.evaluated_count == 2


def test_coverage_positional_and_sets():
    cov = CoverageReport({"x", "y"}, {"x"})
    assert cov.uncovered_rule_count == 1


def test_recall_over_known_risk_set():
    cov = CoverageReport(registered=["r1", "r2", "r3"], evaluated=["r1"])
    # recall uses registered (known risks covered by redlines), not claim zero miss
    assert cov.recall({"r1", "r2", "r4"}) == 2 / 3
    assert cov.recall({"r9"}) == 0.0
    assert cov.recall(set()) == 1.0


def test_no_forbidden_names():
    import st_platform.safety.coverage as c
    assert not hasattr(c, "zero_miss")
    assert not hasattr(c, "perfect_recall")
