from dataclasses import dataclass

import pytest

from st_platform.common.types import SafetyVerdictTier
from st_platform.report.report import (
    ReportError,
    ReportRenderer,
    ReproducibilityMeta,
)
from st_platform.safety.checker import SafetyChecker
from st_platform.safety.rules import DiagnosticRedline


@dataclass
class FakeResult:
    test_name: str
    p_raw: float
    p_corrected: float


def _meta(**overrides):
    base = {
        "model_version": "mv",
        "dataset_version": "dv",
        "dataset_sha": "sha",
        "code_version": "cv",
        "seed": 7,
        "contamination_result": {"contaminated": False},
    }
    base.update(overrides)
    return ReproducibilityMeta(**base)


def test_validate_complete_ok():
    m = _meta()
    m.validate_complete()  # no raise


@pytest.mark.parametrize("field", ["model_version", "dataset_version", "dataset_sha", "code_version", "seed"])
def test_validate_complete_rejects_missing(field):
    m = _meta(**{field: None})
    # seed case: also empty string
    if field == "seed":
        m = _meta(seed="")
    with pytest.raises(ReportError):
        m.validate_complete()
    # also empty string for str fields
    if field != "seed":
        m2 = _meta(**{field: ""})
        with pytest.raises(ReportError):
            m2.validate_complete()


def test_validate_seed_zero_allowed():
    m = _meta(seed=0)
    m.validate_complete()


def test_render_markdown_basic():
    meta = _meta()
    rules = [DiagnosticRedline(id="r", severity=SafetyVerdictTier.BLOCK, description="")]
    checker = SafetyChecker(rules)
    cov = None
    from st_platform.safety.coverage import CoverageReport
    cov = CoverageReport(registered=rules, evaluated=rules)
    verdict = checker.check(results_by_rule={"r": False}, coverage=cov)
    results = [FakeResult("t", 0.01, 0.04)]
    renderer = ReportRenderer()
    md = renderer.render_markdown(
        repro=meta,
        results=results,
        verdict=verdict,
        accuracy_before=0.8,
        accuracy_after=0.9,
    )
    assert "model_version: mv" in md
    assert "dataset_sha: sha" in md
    assert "p_raw" in md and "p_corrected" in md
    assert "0.01" in md and "0.04" in md
    assert "Guardrail verdict" in md
    assert True
    # guardrail separate from effectiveness
    assert md.index("Guardrail verdict") < md.index("Effectiveness")


def test_render_rejects_missing_meta():
    renderer = ReportRenderer()
    with pytest.raises(ReportError):
        renderer.render_markdown(results=[], verdict=None)


def test_render_flags_low_kappa():
    meta = _meta()
    subsets = [{"name": "dept-A", "kappa": 0.4}]
    renderer = ReportRenderer()
    md = renderer.render_markdown(repro=meta, results=[], low_kappa_subsets=subsets)
    assert "结论仅供参考" in md
    assert "dept-A" in md


def test_render_flags_low_kappa_nested_annotation():
    meta = _meta()
    @dataclass
    class S:
        name: str
        annotation: object
    s = S(name="subset-x", annotation=type("A", (), {"kappa": 0.2})())
    renderer = ReportRenderer()
    md = renderer.render_markdown(repro=meta, results=[], kappa_subsets=[s], kappa_threshold=0.6)
    assert "结论仅供参考" in md


def test_render_missing_repro_element_rejected():
    meta = _meta(model_version="")
    renderer = ReportRenderer()
    with pytest.raises(ReportError):
        renderer.render_markdown(repro=meta, results=[])
