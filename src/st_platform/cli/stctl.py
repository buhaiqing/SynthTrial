"""stctl — SynthTrial P0 CLI (Slice 5). Vertical slice end-to-end."""

from __future__ import annotations

import argparse
import json
import sys

from st_platform.audit.ledger import AuditLedger
from st_platform.common.types import sha256_hex
from st_platform.dataset.core import Dataset, DatasetSplit, contamination_detect
from st_platform.infer.multicorrect import bonferroni
from st_platform.infer.paired import mcnemar, paired_t_test
from st_platform.infer.result import PairedResult
from st_platform.registry.metrics import MetricDefinition, MetricKind, MetricRegistry
from st_platform.report.report import ReportRenderer, ReproducibilityMeta
from st_platform.safety.checker import SafetyChecker
from st_platform.safety.rules import DiagnosticRedline
from st_platform.store import ReportStore


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
    contamination = contamination_detect(ds, set())

    labels = [r["label"] for r in ds.rows]
    before = [_baseline_pred(r) for r in ds.rows]
    after = [_candidate_pred(r) for r in ds.rows]

    acc_before = sum(a == b for a, b in zip(before, labels)) / len(labels)
    acc_after = sum(a == b for a, b in zip(after, labels)) / len(labels)

    t_res = paired_t_test(
        [float(a == b) for a, b in zip(before, labels)],
        [float(a == b) for a, b in zip(after, labels)],
    )
    mc_res = mcnemar(before, after)

    raw_ps = [t_res["p_value"], mc_res["p_value"]]
    corrected = bonferroni(raw_ps)

    results = [
        PairedResult(
            test_name="accuracy",
            n=len(labels),
            statistic=t_res["statistic"],
            p_raw=raw_ps[0],
            p_corrected=corrected[0],
            method="paired_t_test",
            ci_low=0.0,
            ci_high=1.0,
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
            ci_low=0.0,
            ci_high=1.0,
            abs_lift=acc_after - acc_before,
            rel_lift=0.0,
            correction_applied="bonferroni",
        ),
    ]

    redlines = [DiagnosticRedline(id="rl.no_missed_critical", severity_level="BLOCK")]
    checker = SafetyChecker(redlines)
    verdict = checker.check(
        results_by_rule={"rl.no_missed_critical": bool(contamination["contaminated"])},
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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "demo":
        return cmd_demo(args)
    if args.cmd == "reports":
        return cmd_reports(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
