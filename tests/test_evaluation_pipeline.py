"""Slice 6 — offline evaluation pipeline, end to end (real runners, real store).

Every test walks the production path: real ``MockRunner`` instances, a real
``Dataset``, the real ``TaskService`` snapshot, the real ``SafetyChecker`` and a
real ``ReportStore`` on disk. Nothing under test is monkey-patched.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from st_platform.audit.ledger import AuditLedger
from st_platform.common.types import SafetyVerdictTier
from st_platform.dataset.core import Dataset, DatasetSplit, case_signature, contamination_violated
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
    """Registered redline with a real evaluator: fires when the eval set leaks train data.

    Reads the detection result through ``contamination_violated`` — the single reader of
    that shape — so this rule and stctl's agree that an unknown conclusion is a violation
    rather than a clean one (T-M7-11).
    """

    id = "rl.eval_contamination"
    severity = SafetyVerdictTier.BLOCK
    description = "eval samples must not overlap the training corpus"

    def evaluate(self, evidence: dict) -> bool:
        return contamination_violated(evidence["contamination"])


class WarnRedline:
    """WARN-tier rule that always fires: needs a human approver, not an automatic yes."""

    id = "rl.coverage_gap"
    severity = SafetyVerdictTier.WARN
    description = "subgroup coverage below target"

    def evaluate(self, evidence: dict) -> bool:
        return True


class MetadataOnlyRedline:
    """Registered but with no evaluator: must never be mistaken for a PASS."""

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


def clean_train_signatures() -> list[str]:
    """A supplied training corpus that does not overlap the eval set.

    A *measured* clean claim. Passing nothing instead means 'no corpus was supplied',
    which must block instead of certifying cleanliness (T-M7-11) — so tests that assert a
    PASS verdict have to supply this rather than rely on the absence of a corpus.
    """
    return [case_signature({"case_id": "TRAIN-ONLY", "text": "not in the eval set"})]


def run_once(
    store: ReportStore,
    *,
    redlines: list | None = None,
    metrics: list[MetricDefinition] | None = None,
    candidate_runner: MockRunner | None = None,
    params: dict | None = None,
    train_signatures: list[str] | None = None,
    ledger: AuditLedger | None = None,
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
        ledger=ledger,
    )


def test_pipeline_records_the_evaluation_in_the_audit_ledger(tmp_path):
    """T-M7-12: the real evaluation path must leave recoverable evidence.

    ``AuditLedger`` previously had exactly one caller -- ``cmd_demo`` -- so ``cmd_run``
    wrote no audit events at all and the ledger named in design.md 4.1 was decoration.
    """
    store = ReportStore(tmp_path / "reports")
    ledger = AuditLedger(path=tmp_path / "audit.jsonl")
    outcome = run_once(store, train_signatures=clean_train_signatures(), ledger=ledger)

    assert ledger.verify() is True
    types = [e.event_type for e in ledger.entries]
    assert "evaluation.completed" in types, f"pipeline must record its verdict: {types}"
    ev = ledger.entries[types.index("evaluation.completed")]
    assert ev.payload["report_hash"] == outcome.report_hash
    assert ev.payload["verdict"] == outcome.verdict.tier.value
    assert ev.payload["task_id"] == outcome.task_id
    # and it survives the process that wrote it
    assert AuditLedger(path=tmp_path / "audit.jsonl").verify() is True


def test_audit_timestamps_do_not_leak_into_the_report_hash(tmp_path):
    """Every ledger entry carries ``created_at``; that must not perturb report_hash.

    Identical inputs must still replay to an identical report (design.md 4.1), even
    though the two runs below were audited at different instants.
    """
    a = run_once(
        ReportStore(tmp_path / "s1"),
        train_signatures=clean_train_signatures(),
        ledger=AuditLedger(path=tmp_path / "a.jsonl"),
    )
    b = run_once(
        ReportStore(tmp_path / "s2"),
        train_signatures=clean_train_signatures(),
        ledger=AuditLedger(path=tmp_path / "b.jsonl"),
    )
    assert a.report_hash == b.report_hash, "an audit timestamp must not change the report"


# (a) clean PASS run ---------------------------------------------------------


def test_clean_run_promotes_and_persists_report(tmp_path):
    store = ReportStore(tmp_path / "reports")
    outcome = run_once(store, train_signatures=clean_train_signatures())

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
    # run_once supplies no training corpus, so the honest conclusion is unknown.
    # It used to assert `contaminated is False`, which certified a check that
    # never ran (design.md 3.2: not-seen is not unseen).
    assert repro.contamination_result["train_corpus_supplied"] is False
    assert repro.contamination_result["contaminated"] is None
    assert repro.contamination_result["train_overlap_count"] is None
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


def test_unchecked_contamination_blocks_instead_of_certifying_clean(tmp_path):
    """T-M7-11: with no training corpus the conclusion is unknown, and unknown must not promote.

    Reproduced on main: a run with no corpus reported ``train_overlap_count=0``,
    ``contaminated=False`` and ``promotable=True`` -- certifying a check that never ran
    (design.md §3.2; CP-7: record 「没采到」 as null, not as 0).
    """
    store = ReportStore(tmp_path / "reports")
    outcome = run_once(store)  # no train_signatures at all

    cr = outcome.reproducibility.contamination_result
    assert cr["train_corpus_supplied"] is False
    assert cr["contaminated"] is None, "an unmeasured conclusion must stay unknown"
    assert cr["train_overlap_count"] is None, "an unmeasured count must be null, not 0"

    assert outcome.verdict.tier == SafetyVerdictTier.BLOCK
    assert outcome.verdict.blocking_ids == ("rl.eval_contamination",)
    assert outcome.promotable is False

    # a veto on promotion is not a reason to lose the effectiveness evidence
    assert len(outcome.results) == 2
    assert outcome.accuracy_before is not None
    assert store.exists(outcome.report_hash)


def test_warn_rule_requires_human_approval(tmp_path):
    store = ReportStore(tmp_path / "reports")
    outcome = run_once(
        store,
        redlines=[ContaminationRedline(), WarnRedline()],
        train_signatures=clean_train_signatures(),
    )

    assert outcome.verdict.tier == SafetyVerdictTier.WARN
    assert outcome.verdict.warning_ids == ("rl.coverage_gap",)
    assert outcome.promotable is False  # WARN is not an automatic yes


def test_finished_outcome_cannot_be_rewritten(tmp_path):
    """D-3: a completed result is not overwritable -- not even the one-vote veto.

    Scope of the promise: attribute rebinding, the nested guardrail verdict and the
    contamination record are immutable. ``results`` is spec-typed ``list[PairedResult]``
    and therefore remains a mutable list by contract (documented residual risk).
    """
    store = ReportStore(tmp_path / "reports")
    outcome = run_once(store, train_signatures=clean_train_signatures())

    with pytest.raises(ValidationError):
        outcome.verdict.tier = SafetyVerdictTier.BLOCK
    with pytest.raises(ValidationError):
        outcome.report_markdown = "tampered"
    # the nested verdict is a frozen snapshot too: no mutable container left inside it
    # (tuple, not FrozenDict — so the mutator is absent, not merely refusing)
    assert outcome.verdict.blocking_ids == ()
    assert not hasattr(outcome.verdict.blocking_ids, "append")
    with pytest.raises(AttributeError):
        outcome.verdict.blocking_ids.append("rl.fake")  # type: ignore[attr-defined]


def test_contamination_record_cannot_be_tampered(tmp_path):
    """The contamination conclusion is evidence; it must not be editable in place."""
    store = ReportStore(tmp_path / "reports")
    outcome = run_once(store)
    with pytest.raises(TypeError):
        outcome.reproducibility.contamination_result["contaminated"] = True


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


def test_unevaluated_registered_redline_is_rejected(tmp_path):
    """An unevaluated redline is not a PASS (design §7: registered-set recall = 100%)."""
    store = ReportStore(tmp_path / "reports")
    with pytest.raises(EvaluationError):
        run_once(store, redlines=[ContaminationRedline(), MetadataOnlyRedline()])
    assert store.list_hashes() == []


def test_block_rule_without_evaluator_cannot_silently_promote(tmp_path):
    """Critic-R1 BLOCKER, reproduced: a registered BLOCK redline with no evaluator plus
    40/40 real training contamination used to yield tier=PASS and promotable=True.
    Unevaluated must fail loudly instead of promoting (M006: 检测必须命中，不得静默通过).
    """
    store = ReportStore(tmp_path / "reports")
    dataset = make_dataset()
    leaks = [case_signature(row) for row in dataset.rows]  # every eval sample leaked
    with pytest.raises(EvaluationError):
        run_once(
            store,
            redlines=[DiagnosticRedline(id="rl.no_missed_critical", severity_level="BLOCK")],
            train_signatures=leaks,
        )
    assert store.list_hashes() == []


def test_dataset_must_match_task_snapshot(tmp_path):
    """Critic-R1 MAJOR: the report printed the snapshot's dataset_sha while a different
    dataset was actually evaluated. §4.1: the report must answer "how was this scored".

    Each dimension is exercised on its own: mutating only the id/version (keeping rows
    identical, hence sha identical) is verified by mutation testing, so a future
    "compare the sha only" regression cannot pass silently.
    """
    snapshot_dataset = make_dataset()
    task = make_task(snapshot_dataset)
    variants = {
        "different rows (sha)": {"rows": snapshot_dataset.rows[:5], "sha256": ""},
        "same rows, different id": {"dataset_id": "cards-RENAMED"},
        "same rows, different version": {"version": 2},
    }
    for label, update in variants.items():
        store = ReportStore(tmp_path / label.replace(" ", "_").replace(",", ""))
        other = snapshot_dataset.model_copy(update=update)
        baseline, candidate = make_runners()
        with pytest.raises(EvaluationError):
            EvaluationPipeline().run(
                task=task,
                dataset=other,
                baseline_runner=baseline,
                candidate_runner=candidate,
                metrics=make_metrics(),
                redlines=[ContaminationRedline()],
                store=store,
            )
        assert store.list_hashes() == [], label


def test_report_carries_effect_size_and_ci(tmp_path):
    """Critic-R1 MAJOR: the report rendered p-values only (M003 F4: 效应量 + 区间,
    不只报 p 值; §7: 绝对提升率 + 95% CI 才可验收).
    """
    store = ReportStore(tmp_path / "reports")
    outcome = run_once(store)
    md = outcome.report_markdown
    assert "Effect size" in md and "95% CI" in md
    for result in outcome.results:
        assert f"{result.ci_low:.6g}" in md
        assert f"{result.ci_high:.6g}" in md
        assert f"{result.abs_lift:.6g}" in md


def test_non_numeric_metric_kind_is_rejected(tmp_path):
    """Critic-R1 MINOR: a TEXT metric was silently coerced to a number and t-tested."""
    store = ReportStore(tmp_path / "reports")
    text_metric = MetricDefinition(
        metric_id="m.note", name="note", kind=MetricKind.TEXT, owner="st-ledger"
    )
    with pytest.raises(EvaluationError):
        run_once(store, metrics=[text_metric])
    assert store.list_hashes() == []


def test_content_hash_addresses_task_snapshot_not_run_inputs(tmp_path):
    """Pinned contract (Critic-R1 F5): metrics/redlines are NOT part of ``content_hash``;
    ``report_hash`` is the per-evaluation address used for result caching."""
    with_2 = run_once(ReportStore(tmp_path / "a"))
    with_1 = run_once(ReportStore(tmp_path / "b"), metrics=make_metrics()[:1])
    assert with_2.content_hash == with_1.content_hash  # same task snapshot
    assert with_2.report_hash != with_1.report_hash  # different evaluation inputs


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
