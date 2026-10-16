"""Slice 6 — offline evaluation pipeline, end to end (real runners, real store).

Every test walks the production path: real ``MockRunner`` instances, a real
``Dataset``, the real ``TaskService`` snapshot, the real ``SafetyChecker`` and a
real ``ReportStore`` on disk. Nothing under test is monkey-patched.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from st_platform.common.types import SafetyVerdictTier
from st_platform.dataset.core import Dataset, DatasetSplit, case_signature
from st_platform.evaluation import (
    EvaluationError,
    EvaluationOutcome,
    EvaluationPipeline,
    UnalignedCases,
)
from st_platform.inference.runner import MockRunner
from st_platform.registry.metrics import MetricDefinition, MetricKind, MetricRegistry
from st_platform.safety.rules import DiagnosticRedline
from st_platform.store import ReportStore
from st_platform.task.models import Task
from st_platform.task.service import TaskService

BASELINE_VERSION = "base-v1"
CANDIDATE_VERSION = "cand-v2"


class ContaminationRedline:
    """Registered redline with a real evaluator: fires when the eval set leaks train data."""

    id = "rl.eval_contamination"
    severity = SafetyVerdictTier.BLOCK
    description = "eval samples must not overlap the training corpus"

    def evaluate(self, evidence: dict) -> bool:
        return bool(evidence["contamination"]["contaminated"])


class WarnRedline:
    """WARN-tier rule that always fires: needs a human approver, not an automatic yes."""

    id = "rl.coverage_gap"
    severity = SafetyVerdictTier.WARN
    description = "subgroup coverage below target"

    def evaluate(self, evidence: dict) -> bool:
        return True


class MetadataOnlyRedline:
    """Registered but not evaluated: must surface as uncovered, never as a silent PASS."""

    id = "rl.hand_review"
    severity = SafetyVerdictTier.WARN
    description = "requires manual chart review"


class RenamingRunner(MockRunner):
    """Deliberately violates the runner contract: reports case ids the dataset never had."""

    def predict(self, row: dict) -> dict:
        pred = super().predict(row)
        pred["case_id"] = f"{pred['case_id']}@renamed"
        return pred


def make_dataset(n: int = 40) -> Dataset:
    rows = [
        {
            "case_id": f"C{i:03d}",
            "text": f"患者主诉 {i} 号样例",
            "label": i % 2,  # ground truth, binary
            "age": 30 + (i % 40),
            "dept": ["内科", "外科", "影像科"][i % 3],
        }
        for i in range(n)
    ]
    return Dataset(
        dataset_id="cards-1.0",
        version=1,
        source="hospital-A",
        split=DatasetSplit.EVAL,
        rows=rows,
    )


def make_metrics() -> list[MetricDefinition]:
    """Two registered metrics: one binary (RATE) + one continuous (SCORE)."""
    registry = MetricRegistry()
    accuracy = registry.register(
        MetricDefinition(
            metric_id="m.acc", name="accuracy", kind=MetricKind.RATE, owner="st-ledger"
        )
    )
    score = registry.register(
        MetricDefinition(
            metric_id="m.score", name="diagnostic_score", kind=MetricKind.SCORE, owner="st-ledger"
        )
    )
    return [accuracy, score]


def make_task(dataset: Dataset, *, params: dict | None = None) -> Task:
    return TaskService().submit(
        model_version=CANDIDATE_VERSION,
        dataset=dataset,
        seed=42,
        params={"baseline_model_version": BASELINE_VERSION, **(params or {})},
    )


def make_runners() -> tuple[MockRunner, MockRunner]:
    return (
        MockRunner(model_version=BASELINE_VERSION),
        MockRunner(model_version=CANDIDATE_VERSION),
    )


def run_once(
    store: ReportStore,
    *,
    redlines: list | None = None,
    metrics: list[MetricDefinition] | None = None,
    candidate_runner: MockRunner | None = None,
    params: dict | None = None,
    train_signatures: list[str] | None = None,
) -> EvaluationOutcome:
    """One full run over freshly built (but content-identical) inputs."""
    dataset = make_dataset()
    task = make_task(dataset, params=params)
    baseline, candidate = make_runners()
    return EvaluationPipeline().run(
        task=task,
        dataset=dataset,
        baseline_runner=baseline,
        candidate_runner=candidate_runner or candidate,
        metrics=metrics if metrics is not None else make_metrics(),
        redlines=redlines if redlines is not None else [ContaminationRedline()],
        store=store,
        train_signatures=train_signatures,
    )


# (a) clean PASS run ---------------------------------------------------------


def test_clean_run_promotes_and_persists_report(tmp_path):
    store = ReportStore(tmp_path / "reports")
    outcome = run_once(store)

    assert isinstance(outcome, EvaluationOutcome)
    assert outcome.verdict.tier == SafetyVerdictTier.PASS
    assert outcome.promotable is True

    # report renders both halves, guardrail first (design §4.2)
    md = outcome.report_markdown
    assert "## Guardrail verdict" in md
    assert "## Effectiveness" in md
    assert md.index("Guardrail verdict") < md.index("Effectiveness")

    # persisted under its content hash, readable back
    assert store.exists(outcome.report_hash)
    stored = store.get(outcome.report_hash)
    assert stored["task_id"] == outcome.task_id
    assert stored["report_markdown"] == md
    assert stored["verdict"] == "PASS"
    assert stored["content_hash"] == outcome.content_hash


def test_clean_run_pairs_by_case_id_and_reports_accuracy(tmp_path):
    store = ReportStore(tmp_path / "reports")
    outcome = run_once(store)

    assert len(outcome.results) == 2
    by_name = {r.test_name: r for r in outcome.results}
    assert set(by_name) == {"m.acc@1", "m.score@1"}
    # binary metric -> McNemar; continuous metric -> paired t-test
    assert by_name["m.acc@1"].method == "mcnemar"
    assert by_name["m.score@1"].method == "paired_t_test"
    assert all(r.n == 40 for r in outcome.results)

    # accuracy is measured against ground truth, not against the other model
    assert outcome.accuracy_before is not None and outcome.accuracy_after is not None
    assert 0.0 <= outcome.accuracy_before <= 1.0
    assert 0.0 <= outcome.accuracy_after <= 1.0
    assert "Accuracy before" in outcome.report_markdown


def test_reproducibility_five_elements_are_rendered(tmp_path):
    store = ReportStore(tmp_path / "reports")
    dataset = make_dataset()
    task = make_task(dataset)
    outcome = run_once(store)

    repro = outcome.reproducibility
    repro.validate_complete()
    assert repro.model_version == CANDIDATE_VERSION
    assert repro.dataset_version == f"{dataset.dataset_id}@{dataset.version}"
    assert repro.dataset_sha == task.dataset_sha
    assert repro.seed == 42
    assert repro.code_version
    # contamination travels with the report, even when nothing overlapped
    assert repro.contamination_result["contaminated"] is False
    for line in ("model_version:", "dataset_version:", "dataset_sha:", "code_version:", "seed:"):
        assert line in outcome.report_markdown


# (b) BLOCK redline ----------------------------------------------------------


def test_block_redline_is_not_promotable_and_report_still_renders(tmp_path):
    store = ReportStore(tmp_path / "reports")
    dataset = make_dataset()
    leak = case_signature(dataset.rows[0])  # one eval sample is in the training corpus
    outcome = run_once(store, train_signatures=[leak])

    assert outcome.verdict.tier == SafetyVerdictTier.BLOCK
    assert outcome.verdict.blocking_ids == ("rl.eval_contamination",)
    assert outcome.promotable is False

    md = outcome.report_markdown
    assert "BLOCK" in md and "rl.eval_contamination" in md
    # a BLOCK is a veto on promotion, not a reason to lose the evidence
    assert outcome.results and len(outcome.results) == 2
    assert "## Effectiveness" in md
    assert outcome.reproducibility.contamination_result["contaminated"] is True

    assert store.exists(outcome.report_hash)
    assert store.get(outcome.report_hash)["blocking_ids"] == ["rl.eval_contamination"]


def test_warn_rule_requires_human_approval(tmp_path):
    store = ReportStore(tmp_path / "reports")
    outcome = run_once(store, redlines=[ContaminationRedline(), WarnRedline()])

    assert outcome.verdict.tier == SafetyVerdictTier.WARN
    assert outcome.verdict.warning_ids == ("rl.coverage_gap",)
    assert outcome.promotable is False  # WARN is not an automatic yes


def test_finished_outcome_cannot_be_rewritten(tmp_path):
    """D-3: a completed result is not overwritable -- not even the one-vote veto."""
    store = ReportStore(tmp_path / "reports")
    outcome = run_once(store)

    with pytest.raises(ValidationError):
        outcome.verdict.tier = SafetyVerdictTier.BLOCK
    with pytest.raises(ValidationError):
        outcome.report_markdown = "tampered"
    # the nested verdict is a frozen snapshot too: no mutable container left inside it
    assert outcome.verdict.blocking_ids == ()
    with pytest.raises(AttributeError):
        outcome.verdict.blocking_ids.append("rl.fake")


# (c) multiple-comparison correction -----------------------------------------


def test_correction_is_applied_to_every_result(tmp_path):
    store = ReportStore(tmp_path / "reports")
    outcome = run_once(store)

    tests_run = len(outcome.results)
    assert tests_run >= 2
    for result in outcome.results:
        assert result.p_corrected is not None, "correction is mandatory, not optional"
        assert result.correction_applied == "bonferroni"
        assert result.p_corrected >= result.p_raw
        assert result.p_corrected == pytest.approx(
            min(1.0, tests_run * result.p_raw), rel=1e-9, abs=1e-12
        )


# (d) alignment failure ------------------------------------------------------


def test_mismatched_case_id_sets_raise_and_persist_nothing(tmp_path):
    store = ReportStore(tmp_path / "reports")
    with pytest.raises(UnalignedCases):
        run_once(store, candidate_runner=RenamingRunner(model_version=CANDIDATE_VERSION))
    assert store.list_hashes() == []


# (e) determinism ------------------------------------------------------------


def test_identical_inputs_produce_identical_report_hash(tmp_path):
    store = ReportStore(tmp_path / "reports")
    first = run_once(store)
    second = run_once(store)

    assert first.report_hash == second.report_hash
    assert first.report_markdown == second.report_markdown
    # one address, one stored report: a drifting payload would have raised StoreConflict
    assert store.list_hashes() == [first.report_hash]


# coverage accounting --------------------------------------------------------


def test_rule_without_evaluator_is_counted_uncovered(tmp_path):
    store = ReportStore(tmp_path / "reports")
    outcome = run_once(store, redlines=[ContaminationRedline(), MetadataOnlyRedline()])

    assert outcome.verdict.covered_rule_count == 1
    assert outcome.verdict.uncovered_rule_count == 1
    assert outcome.verdict.uncovered_ratio == pytest.approx(0.5)
    assert "Uncovered rules: 1" in outcome.report_markdown
    assert outcome.promotable is True  # nothing fired; the gap is visible, not hidden


def test_degenerate_runs_are_rejected(tmp_path):
    store = ReportStore(tmp_path / "reports")
    with pytest.raises(EvaluationError):
        run_once(store, metrics=[])
    with pytest.raises(EvaluationError):
        run_once(store, redlines=[])


def test_unknown_correction_method_is_rejected(tmp_path):
    store = ReportStore(tmp_path / "reports")
    with pytest.raises(EvaluationError):
        EvaluationPipeline(correction="no-such-method").run(
            task=make_task(ds := make_dataset()),
            dataset=ds,
            baseline_runner=make_runners()[0],
            candidate_runner=make_runners()[1],
            metrics=make_metrics(),
            redlines=[DiagnosticRedline(id="rl.x", severity=SafetyVerdictTier.WARN)],
            store=store,
        )
    assert store.list_hashes() == []
