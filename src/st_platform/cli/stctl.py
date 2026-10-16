"""stctl — SynthTrial P0 CLI (Slice 5). Vertical slice end-to-end."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from st_platform.audit.ledger import AuditLedger
from st_platform.common.types import SafetyVerdictTier, sha256_hex
from st_platform.dataset.core import (
    Dataset,
    DatasetSplit,
    case_signature,
    contamination_detect,
    contamination_violated,
)
from st_platform.evaluation.pipeline import EvaluationPipeline
from st_platform.infer import effect
from st_platform.infer.multicorrect import bonferroni
from st_platform.infer.paired import mcnemar, paired_t_test
from st_platform.infer.result import PairedResult, assert_correction_applied
from st_platform.inference.runner import MockRunner
from st_platform.registry.metrics import MetricDefinition, MetricKind, MetricRegistry
from st_platform.report.report import ReportRenderer, ReproducibilityMeta
from st_platform.safety.checker import SafetyChecker
from st_platform.safety.rules import DiagnosticRedline
from st_platform.store import ReportStore
from st_platform.task.models import TaskState
from st_platform.task.service import TaskService


def _demo_dataset(n: int = 40) -> Dataset:
    rows = [
        {
            "case_id": f"C{i:03d}",
            "text": f"患者主诉 {i} 号样例",
            "label": i % 2,  # ground truth binary
            "age": 30 + (i % 40),
            "dept": ["内科", "外科", "影像科"][i % 3],
        }
        for i in range(n)
    ]
    return Dataset(
        dataset_id="cards-demo",
        version=1,
        source="synthetic",
        split=DatasetSplit.EVAL,
        rows=rows,
    )


def _digest(row: dict) -> int:
    """Stable across processes. Built-in hash() is salted per interpreter run
    (PYTHONHASHSEED), which silently changed every number in the report."""
    return int(sha256_hex(row["case_id"])[:8], 16)


def _baseline_pred(row: dict) -> int:
    """Baseline model: correct unless the stable digest says otherwise."""
    return int(row["label"]) if _digest(row) % 5 else 1 - int(row["label"])


def _candidate_pred(row: dict) -> int:
    """Candidate model: repairs a subset of the baseline's errors.

    Guarantees candidate accuracy >= baseline accuracy, so the demo actually
    exercises the paired test rather than showing a regression.
    """
    base = _baseline_pred(row)
    if base != int(row["label"]) and _digest(row) % 3 == 0:
        return int(row["label"])
    return base


def cmd_demo(args: argparse.Namespace) -> int:
    reg = MetricRegistry()
    reg.register(
        MetricDefinition(
            metric_id="m.acc",
            name="accuracy",
            kind=MetricKind.RATE,
            owner="st-registry",
        )
    )
    reg.register(
        MetricDefinition(
            metric_id="m.diag_agree",
            name="diagnosis_agreement",
            kind=MetricKind.RATE,
            owner="st-ledger",
        )
    )

    ds = _demo_dataset(args.n)
    # No real training corpus exists at P0, so the demo synthesizes its own:
    # the first rows double as "training" rows, which makes the guardrail able to
    # fire instead of demonstrating a check that can never trip. Deterministic
    # by construction (case_signature, not hash()).
    contamination = contamination_detect(ds, {case_signature(r) for r in ds.rows[:3]})

    labels = [r["label"] for r in ds.rows]
    before = [_baseline_pred(r) for r in ds.rows]
    after = [_candidate_pred(r) for r in ds.rows]

    acc_before = sum(a == b for a, b in zip(before, labels)) / len(labels)
    acc_after = sum(a == b for a, b in zip(after, labels)) / len(labels)

    before_correct = [float(a == b) for a, b in zip(before, labels)]
    after_correct = [float(a == b) for a, b in zip(after, labels)]

    t_res = paired_t_test(before_correct, after_correct)
    mc_res = mcnemar(before, after)

    raw_ps = [t_res["p_value"], mc_res["p_value"]]
    corrected = bonferroni(raw_ps)

    acc_ci_low, acc_ci_high = float(t_res["ci_low"]), float(t_res["ci_high"])
    agree_ci_low, agree_ci_high = effect.absolute_lift_ci95(
        [float(x) for x in before], [float(x) for x in after]
    )

    results = [
        PairedResult(
            test_name="accuracy",
            n=len(labels),
            statistic=t_res["statistic"],
            p_raw=raw_ps[0],
            p_corrected=corrected[0],
            method="paired_t_test",
            ci_low=acc_ci_low,
            ci_high=acc_ci_high,
            abs_lift=acc_after - acc_before,
            rel_lift=(acc_after - acc_before) / acc_before if acc_before else 0.0,
            correction_applied="bonferroni",
        ),
        PairedResult(
            test_name="binary_agreement",
            n=len(labels),
            statistic=mc_res["statistic"],
            p_raw=raw_ps[1],
            p_corrected=corrected[1],
            method="mcnemar",
            ci_low=agree_ci_low,
            ci_high=agree_ci_high,
            abs_lift=acc_after - acc_before,
            rel_lift=0.0,
            correction_applied="bonferroni",
        ),
    ]
    assert_correction_applied(results)

    redlines = [DiagnosticRedline(id="rl.no_missed_critical", severity_level="BLOCK")]
    checker = SafetyChecker(redlines)
    verdict = checker.check(
        # via the shared reader, like every other redline: `bool(contamination[...])` here
        # would be a second, fail-open interpretation of the same shape (T-M7-11)
        results_by_rule={"rl.no_missed_critical": contamination_violated(contamination)},
        registered_count=len(redlines),
        evaluated_count=len(redlines),
    )

    repro = ReproducibilityMeta(
        model_version="model-v2.0.0",
        dataset_version=f"{ds.dataset_id}@{ds.version}",
        dataset_sha=ds.compute_sha(),
        code_version="st-platform@0.1.0",
        seed=42,
        contamination_result=contamination,
    )
    repro.validate_complete()

    renderer = ReportRenderer()
    md = renderer.render_markdown(
        repro=repro,
        results=results,
        verdict=verdict,
        accuracy_before=acc_before,
        accuracy_after=acc_after,
    )

    audit = AuditLedger()
    audit.append("task.submitted", {"dataset": ds.dataset_id, "n": args.n})
    audit.append("task.completed", {"verdict": verdict.tier.value})
    assert audit.verify()

    if args.json:
        print(
            json.dumps({"verdict": verdict.tier.value, "report": md}, ensure_ascii=False, indent=2)
        )
    else:
        print(md)
    return 0


DEFAULT_STORE_DIR = "reports"

#: Audit trail written beside the reports. ".jsonl" is deliberate, not cosmetic:
#: ReportStore.list_hashes() globs "*.json", so a ".json" audit file would be listed
#: by `stctl reports` as if it were an evaluation result.
AUDIT_LOG_NAME = "audit.jsonl"


def cmd_reports(args: argparse.Namespace) -> int:
    """List reports persisted in a ReportStore.

    Sorted by created_at descending where available (newest first). Exit code
    is 0 as long as the store is *readable*; a corrupt entry is surfaced with
    ``corrupt: true``, not hidden, because hiding it would make the listing
    untrustworthy.
    """
    store = ReportStore(getattr(args, "store", None) or DEFAULT_STORE_DIR)
    rows = store.summaries()

    def _sort_key(row: dict) -> str:
        created = row.get("created_at")
        return str(created) if created is not None else ""

    rows = sorted(rows, key=_sort_key, reverse=True)

    if getattr(args, "json", False):
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if not rows:
        print("no reports in store")
        return 0

    for row in rows:
        flag = " [CORRUPT]" if row.get("corrupt") else ""
        line = (
            f"{row.get('created_at', '?')}  {row.get('task_id', '?')}  "
            f"{row.get('model_version', '?')}  {row.get('verdict', '?')}{flag}"
        )
        print(line)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stctl", description="SynthTrial P0 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="run an end-to-end demo evaluation")
    d.add_argument("--n", type=int, default=40, help="dataset size")
    d.add_argument("--json", action="store_true", help="output JSON")
    r = sub.add_parser("reports", help="list persisted reports")
    r.add_argument("--store", default=DEFAULT_STORE_DIR, help="report store directory")
    r.add_argument("--json", action="store_true", help="output JSON")

    run_p = sub.add_parser("run", help="run the evaluation pipeline and persist a report")
    run_p.add_argument(
        "--dataset", required=True, help="evaluation dataset JSON (see `stctl sample`)"
    )
    run_p.add_argument("--model-version", required=True, help="candidate model version")
    run_p.add_argument("--baseline-version", default="baseline", help="baseline model version")
    run_p.add_argument("--store", default=DEFAULT_STORE_DIR, help="report store directory")
    run_p.add_argument("--seed", type=int, default=0)
    run_p.add_argument(
        "--train-signatures",
        default=None,
        help=(
            "JSON file of training-set case signatures "
            '({"signatures": [...]} or a bare [...]); without it the contamination '
            "check cannot run and the report says so explicitly"
        ),
    )
    run_p.add_argument("--json", action="store_true", help="output JSON")
    run_p.add_argument(
        "--self-test-block",
        action="store_true",
        help="register an always-BLOCK redline to prove the gate can fail (operator smoke test)",
    )

    s_p = sub.add_parser("sample", help="write a deterministic synthetic dataset")
    s_p.add_argument("--out", default="eval-sample.json", help="output path")
    s_p.add_argument("--n", type=int, default=30, help="number of rows")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "demo":
        return cmd_demo(args)
    if args.cmd == "reports":
        return cmd_reports(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "sample":
        return cmd_sample(args)
    return 1


# --------------------------------------------------------------------------
# stctl run / stctl sample
#
# `demo` predates the evaluation pipeline and hand-rolls its statistics, so it
# never creates a Task and never persists anything (ARCHITECTURE.md G-6).
# `run` is the real vertical slice: Task -> pipeline -> ReportStore, with the
# exit code carrying the guardrail verdict so CI can gate on it.
# --------------------------------------------------------------------------


class ContaminationRedline(DiagnosticRedline):
    """BLOCK when the evaluation set overlaps the training corpus.

    design.md §4.4: "不可见 ≠ 未曝光". A contaminated evaluation set cannot
    distinguish memorisation from generalisation, so the report is not evidence
    of anything. Unmeasurable patterns are not claimed to be caught here — this
    rule only fails on contamination it can actually observe.

    It also fails when contamination is **unknown** (no training corpus was
    supplied): an unexcluded overlap is indistinguishable from an absent one, so
    the run must not certify a clean conclusion it never measured (T-M7-11).
    ``contamination_violated`` is the shared reader of the detection shape, so
    this rule and the pipeline agree on what "checked" means.
    """

    def evaluate(self, evidence: dict) -> bool:
        return contamination_violated(evidence.get("contamination"))


class SelfTestBlockRedline(DiagnosticRedline):
    """Always fires. Registered only by ``--self-test-block``.

    A gate nobody has watched fail is a gate nobody can trust: a permanently-PASS
    report is indistinguishable from a broken deployment. This makes the operator
    see a real BLOCK end-to-end before relying on a PASS.
    """

    def evaluate(self, evidence: dict) -> bool:
        return True


def _default_registry() -> MetricRegistry:
    """The metric catalogue a real run is evaluated against (T-M7-13).

    Registered here rather than constructed inline in the run so the pipeline can bind
    every reported number to a registered id+version. P0 seeds this in code; the
    production catalogue is a table (M11).
    """
    registry = MetricRegistry()
    registry.register(
        MetricDefinition(
            metric_id="m.accuracy", name="accuracy", kind=MetricKind.RATE, owner="st-registry"
        )
    )
    registry.register(
        MetricDefinition(
            metric_id="m.score", name="model_score", kind=MetricKind.SCORE, owner="st-registry"
        )
    )
    return registry


def _default_metrics(registry: MetricRegistry) -> list[MetricDefinition]:
    """Two metrics so the run has >1 test and correction is mandatory.

    design.md §3 M003 F3: with a single metric there is nothing to correct, and
    a one-metric run would silently skip the multiple-comparison guard.

    Resolved from ``registry``, so what is measured is what is registered.
    """
    return [
        registry.all_versions("m.accuracy")[0],
        registry.all_versions("m.score")[0],
    ]


def _load_dataset(path) -> Dataset:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Dataset(
        dataset_id=raw.get("dataset_id", "dataset"),
        version=int(raw.get("version", 1)),
        source=raw.get("source", f"file:{path}"),
        split=DatasetSplit.EVAL,
        rows=raw.get("rows", []),
    )


def cmd_sample(args: argparse.Namespace) -> int:
    """Write a deterministic synthetic evaluation set.

    P0 has no data plane (M11), so `run` needs something to read. The output is
    byte-identical for a given --n, which is what makes `run` reproducible.
    """
    n = int(getattr(args, "n", 30))
    rows = [
        {"case_id": f"C{i:04d}", "text": f"合成病例 {i}", "label": i % 2, "age": 30 + i % 40}
        for i in range(n)
    ]
    payload = {"dataset_id": "cards-sample", "version": 1, "rows": rows}
    out = Path(getattr(args, "out", "eval-sample.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {n} rows -> {out}")
    return 0


def _load_train_signatures(path: str | None) -> list[str] | None:
    """Read training-set case signatures. Returns None when not supplied.

    None is meaningful and must stay distinct from an empty list: "no training
    corpus supplied" means the contamination check could not run, which is not
    the same claim as "checked, nothing overlapped".
    """
    if not path:
        return None
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("signatures", [])
    if not isinstance(raw, list):
        raise TypeError(f'{path}: expected a list of signatures or {{"signatures": [...]}}')
    return [str(s) for s in raw]


def cmd_run(args: argparse.Namespace) -> int:
    """Run the real evaluation pipeline and persist the report.

    Exit code is the promotion gate: 0 only when the guardrail verdict is PASS.
    WARN is NOT an automatic yes (design.md §4.2 — it needs a human approver),
    so it exits non-zero rather than pretending the model is promotable.
    """
    ds_path = Path(getattr(args, "dataset", "") or "")
    if not ds_path.exists():
        print(f"error: dataset not found: {ds_path}", file=sys.stderr)
        return 2
    try:
        dataset = _load_dataset(ds_path)
    except (OSError, ValueError) as exc:
        print(f"error: cannot read dataset {ds_path}: {exc}", file=sys.stderr)
        return 2

    candidate_version = getattr(args, "model_version", "candidate")
    baseline_version = getattr(args, "baseline_version", "baseline")
    train_path = getattr(args, "train_signatures", None)
    try:
        train_signatures = _load_train_signatures(train_path)
    except (OSError, ValueError, TypeError) as exc:
        # JSONDecodeError subclasses ValueError, so bad JSON lands here too.
        print(f"error: cannot read --train-signatures {train_path}: {exc}", file=sys.stderr)
        return 2
    service = TaskService()
    store = ReportStore(getattr(args, "store", None) or DEFAULT_STORE_DIR)
    # Durable hash-linked evidence for this run (T-M7-12). Before this, the ledger was
    # constructed only by cmd_demo, so a real evaluation left no audit trail at all.
    ledger = AuditLedger(path=store.root / AUDIT_LOG_NAME)
    # The metric catalogue this run is bound to (T-M7-13). The pipeline re-resolves each
    # metric through it, so a report number always maps to a registered id + version.
    registry = _default_registry()

    task = service.submit(
        model_version=candidate_version,
        dataset=dataset,
        seed=int(getattr(args, "seed", 0)),
        params={"baseline_model_version": baseline_version},
    )
    ledger.append(
        "task.submitted",
        {
            "task_id": task.task_id,
            "content_hash": task.content_hash,
            "model_version": candidate_version,
            "dataset_sha": task.dataset_sha,
            "seed": task.seed,
        },
    )
    task = service.transition(task.task_id, TaskState.RUNNING)

    redlines: list[Any] = [
        ContaminationRedline(
            id="rl.contamination",
            severity=SafetyVerdictTier.BLOCK,
            description="评测集与训练语料重叠",
        )
    ]
    if getattr(args, "self_test_block", False):
        redlines.append(
            SelfTestBlockRedline(
                id="rl.self_test_block",
                severity=SafetyVerdictTier.BLOCK,
                description="--self-test-block: 强制验证护栏可熔断",
            )
        )

    try:
        outcome = EvaluationPipeline().run(
            task=task,
            dataset=dataset,
            baseline_runner=MockRunner(model_version=baseline_version),
            candidate_runner=MockRunner(model_version=candidate_version),
            metrics=_default_metrics(registry),
            registry=registry,
            redlines=redlines,
            store=store,
            train_signatures=train_signatures,
            ledger=ledger,
        )
    except Exception as exc:  # noqa: BLE001 -- CLI boundary: any failure is a FAILED task
        failed = service.transition(task.task_id, TaskState.FAILED)
        # a failure is exactly the kind of event an audit trail exists to keep
        ledger.append(
            "task.failed",
            {"task_id": failed.task_id, "error": f"{type(exc).__name__}: {exc}"},
        )
        print(f"error: task_id={failed.task_id} state=FAILED", file=sys.stderr)
        print(f"       {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    done = service.transition(task.task_id, TaskState.DONE)
    ledger.append(
        "task.completed",
        {
            "task_id": done.task_id,
            "report_hash": outcome.report_hash,
            "verdict": outcome.verdict.tier.value,
            "promotable": outcome.promotable,
        },
    )
    contamination = outcome.reproducibility.contamination_result or {}

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "task_id": done.task_id,
                    "task_state": done.state.value,
                    "content_hash": outcome.content_hash,
                    "report_hash": outcome.report_hash,
                    "verdict": outcome.verdict.tier.value,
                    "promotable": outcome.promotable,
                    "accuracy_before": outcome.accuracy_before,
                    "accuracy_after": outcome.accuracy_after,
                    # unknown stays null: bool() here would re-manufacture the
                    # "checked, clean" claim for a run that never checked (T-M7-11)
                    "contaminated": contamination.get("contaminated"),
                    "contamination_overlap": contamination.get("train_overlap_count"),
                    "train_corpus_supplied": contamination.get("train_corpus_supplied"),
                    "report": outcome.report_markdown,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(outcome.report_markdown)
        print(f"\ntask_id: {done.task_id}  state: {done.state.value}")
        print(f"report_hash: {outcome.report_hash}")

    return 0 if outcome.promotable else 1


if __name__ == "__main__":
    sys.exit(main())
