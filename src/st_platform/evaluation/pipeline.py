"""EvaluationPipeline: the offline evaluation kernel (P0 vertical slice).

One entry point, ``run``, turning a submitted task snapshot into a decision-ready,
content-addressed report artifact. Order of work is fixed (design §3 M006 F1/F3/F4/F5):

1. pair both runners over the SAME dataset rows, keyed by ``case_id`` -- nothing is
   reordered or dropped silently;
2. per-metric paired statistics + mandatory multiple-comparison correction across
   every test in the run (design §3 M003 F3);
3. safety redlines -> ``SafetyVerdict``, kept out of the effectiveness numbers
   (design §4.2);
4. ``ReproducibilityMeta`` built from the task snapshot, ``validate_complete()``d;
5. render + persist the markdown report, return the report text and its store hash.

The stored payload carries no timestamps, so identical inputs replay to an identical
``report_hash`` (design §4.1 + AGENTS §9 A-5).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

from st_platform.api.phi import redact
from st_platform.audit.ledger import AuditLedger
from st_platform.common.freeze import freeze
from st_platform.dataset.core import Dataset, contamination_detect
from st_platform.evaluation.outcome import EvaluationOutcome, GuardrailVerdict
from st_platform.infer import effect, multicorrect
from st_platform.infer.paired import mcnemar, paired_t_test
from st_platform.infer.result import PairedResult, assert_correction_applied
from st_platform.inference.runner import run_batch
from st_platform.registry.metrics import (
    MetricDefinition,
    MetricKind,
    MetricRegistry,
    RegistryError,
)
from st_platform.report.report import ReportRenderer, ReproducibilityMeta
from st_platform.safety.checker import SafetyChecker, SafetyVerdict
from st_platform.store import ReportStore
from st_platform.task.models import Task
from st_platform.version import __version__

#: Dataset row key holding ground truth. Absent => accuracy stays ``None``.
GROUND_TRUTH_KEYS = ("label", "y", "target", "gold")

#: Metric kinds this pipeline can evaluate from the runner contract (``score``/``label``).
#: Anything else is refused loudly: silently coercing e.g. a TEXT metric into a number
#: and t-testing it would put a made-up number into a medical report.
SUPPORTED_METRIC_KINDS: dict[MetricKind, str] = {
    MetricKind.RATE: "label",
    MetricKind.SCORE: "score",
}

#: Significance threshold for the "significant after correction" column (reported next to
#: effect size and CI -- a p-value alone is never the conclusion, design §3 M003 F4).
ALPHA = 0.05

#: Correction methods the pipeline may apply. Bonferroni is the default because the
#: spec names it first and it is the strictest (design §3 M003 F3).
CORRECTIONS: dict[str, Callable[[Iterable[float]], list[float]]] = {
    "bonferroni": multicorrect.bonferroni,
    "holm": multicorrect.holm,
    "fdr_bh": multicorrect.benjamini_hochberg,
}


class EvaluationError(ValueError):
    """The evaluation cannot be produced (bad inputs, not a quality failure)."""


class UnalignedCases(EvaluationError):
    """Baseline and candidate predictions are not aligned on the same case ids."""


def _case_id(row: dict) -> str:
    return str(row.get("case_id", row.get("id", "")))


def _index_by_case(predictions: Sequence[dict], side: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for pred in predictions:
        cid = str(pred.get("case_id", pred.get("id", "")))
        if not cid:
            raise UnalignedCases(f"{side} runner returned a prediction without a case_id")
        if cid in out:
            raise UnalignedCases(f"{side} runner returned case_id {cid!r} twice")
        out[cid] = pred
    return out


def _head(ids: Iterable[str]) -> str:
    listed = sorted(ids)
    return f"{listed[:5]}{' ...' if len(listed) > 5 else ''}" if listed else "none"


class EvaluationPipeline:
    """Runs the offline evaluation kernel end to end."""

    def __init__(self, *, correction: str = "bonferroni") -> None:
        if correction not in CORRECTIONS:
            raise EvaluationError(
                f"unknown correction {correction!r}; available: {sorted(CORRECTIONS)}"
            )
        self.correction = correction

    # ------------------------------------------------------------------ step 1
    def pair_predictions(
        self, dataset: Dataset, baseline_runner: Any, candidate_runner: Any
    ) -> list[tuple[str, dict, dict]]:
        """Run both runners over the same rows and pair by ``case_id``.

        Order follows ``dataset.rows`` so the pairing (and therefore the report) is
        deterministic.
        """
        dataset_ids: list[str] = []
        for row in dataset.rows:
            cid = _case_id(row)
            if not cid:
                raise UnalignedCases("dataset row has no case_id")
            if cid in dataset_ids:
                raise UnalignedCases(f"dataset contains case_id {cid!r} twice")
            dataset_ids.append(cid)

        baseline = _index_by_case(run_batch(baseline_runner, dataset), "baseline")
        candidate = _index_by_case(run_batch(candidate_runner, dataset), "candidate")

        baseline_only = set(baseline) - set(candidate)
        candidate_only = set(candidate) - set(baseline)
        if baseline_only or candidate_only:
            raise UnalignedCases(
                "baseline and candidate results are not the same case set; "
                f"baseline-only: {_head(baseline_only)}; "
                f"candidate-only: {_head(candidate_only)}"
            )
        dropped = set(dataset_ids) - set(baseline)
        if dropped:
            raise UnalignedCases(
                f"runners dropped {len(dropped)} dataset rows; missing case ids: {_head(dropped)}"
            )
        return [(cid, baseline[cid], candidate[cid]) for cid in dataset_ids]

    # ------------------------------------------------------------------ step 2
    def paired_statistics(
        self, pairs: Sequence[tuple[str, dict, dict]], metrics: Sequence[MetricDefinition]
    ) -> list[PairedResult]:
        """One paired test per registered metric, then one mandatory correction pass."""
        if not metrics:
            raise EvaluationError("no metrics supplied; nothing to evaluate")
        results: list[PairedResult] = []
        for metric in metrics:
            before = [self._value(metric, pair[1]) for pair in pairs]
            after = [self._value(metric, pair[2]) for pair in pairs]
            test_name = f"{metric.metric_id}@{metric.version}"
            before_mean = sum(before) / len(before)
            after_mean = sum(after) / len(after)
            if before_mean == 0.0:
                raise EvaluationError(
                    f"metric {test_name}: baseline mean is 0 so relative lift is undefined; "
                    "only the absolute lift would be reportable"
                )

            if metric.kind == MetricKind.RATE:
                # Binary metric: McNemar is the paired test for binary outcomes.
                raw = mcnemar(before, after)
                ci_low, ci_high = effect.absolute_lift_ci95(before, after)
                method = "mcnemar"
            else:
                raw = paired_t_test(before, after)
                ci_low, ci_high = float(raw["ci_low"]), float(raw["ci_high"])
                method = "paired_t_test"

            results.append(
                PairedResult(
                    test_name=test_name,
                    n=len(before),
                    statistic=float(raw["statistic"]),
                    p_raw=float(raw["p_value"]),
                    p_corrected=None,  # filled in for every test below
                    method=method,
                    ci_low=float(ci_low),
                    ci_high=float(ci_high),
                    abs_lift=effect.absolute_lift(before_mean, after_mean),
                    rel_lift=effect.relative_lift(before_mean, after_mean),
                    correction_applied=None,
                )
            )

        # One correction across ALL tests in the run, never per metric in isolation
        # (10 metrics x 8 subgroups = 80 tests otherwise inflates false positives).
        corrected = CORRECTIONS[self.correction]([r.p_raw for r in results])
        results = [
            r.model_copy(update={"p_corrected": p, "correction_applied": self.correction})
            for r, p in zip(results, corrected)
        ]
        assert_correction_applied(results)
        return results

    # ------------------------------------------------------------------ step 3
    def safety_verdict(self, evidence: dict, redlines: Sequence[Any]) -> SafetyVerdict:
        """Evaluate registered redlines; the verdict stays separate from effectiveness.

        Every registered rule must be evaluable (``evaluate(evidence) -> bool``); a
        registered rule without an evaluator aborts the run instead of counting as clean.
        """
        rules = list(redlines)
        if not rules:
            raise EvaluationError("no redlines supplied; an unevaluated guardrail is not a PASS")
        ids = [getattr(rule, "id", None) for rule in rules]
        if any(not rid for rid in ids):
            raise EvaluationError("every registered redline must expose an id")
        if len(set(ids)) != len(ids):
            raise EvaluationError(f"duplicate redline ids: {ids}")

        results_by_rule: dict[str, bool] = {}
        for rule in rules:
            evaluate = getattr(rule, "evaluate", None)
            if evaluate is None:
                # Fail closed. A registered rule that nobody evaluated used to fall
                # through as "not fired" => PASS/promotable (Critic-R1 BLOCKER: a BLOCK
                # redline without an evaluator promoted while 40/40 rows were contaminated).
                # "Not checked" must never be reported as "not crossed" (design §7: the
                # registered set's recall is claimed to be 100%).
                raise EvaluationError(
                    f"redline {rule.id!r} has no evaluate(evidence) hook; an unevaluated "
                    "redline is never a PASS — supply an evaluator (or precomputed results) "
                    "for every registered rule"
                )
            results_by_rule[str(rule.id)] = bool(evaluate(evidence))

        return SafetyChecker(rules).check(results_by_rule=results_by_rule)

    # -------------------------------------------------------------- entry point
    def run(
        self,
        *,
        task: Task,
        dataset: Dataset,
        baseline_runner: Any,
        candidate_runner: Any,
        metrics: Sequence[MetricDefinition],
        redlines: Sequence[Any],
        store: ReportStore,
        registry: MetricRegistry,
        train_signatures: Iterable[str] | None = None,
        ledger: AuditLedger | None = None,
    ) -> EvaluationOutcome:
        """Evaluate the candidate against the baseline and persist the report."""
        self._check_runners(task, baseline_runner, candidate_runner)
        self._check_dataset(task, dataset)

        # Bind metrics to their registered definitions before anything is measured, so
        # an unregistered id or an unrecorded version can never reach a report (T-M7-13).
        metrics = self._resolve_metrics(metrics, registry)

        pairs = self.pair_predictions(dataset, baseline_runner, candidate_runner)
        results = self.paired_statistics(pairs, metrics)

        # Pass ``train_signatures`` through untouched: collapsing None into an empty set
        # here is what let the pipeline certify "not contaminated" for a check that never
        # ran (T-M7-11). None now stays None and reaches the redline as unknown.
        contamination = freeze(contamination_detect(dataset, train_signatures))
        verdict = self.safety_verdict(
            {
                "contamination": contamination,
                "task_id": task.task_id,
                "results_by_metric": {r.test_name: r.model_dump(mode="json") for r in results},
            },
            redlines,
        )

        accuracy_before, accuracy_after = self._accuracy(dataset, pairs)
        repro = ReproducibilityMeta(
            model_version=task.model_version,
            dataset_version=f"{task.dataset_id}@{task.dataset_version}",
            dataset_sha=task.dataset_sha,
            code_version=f"st-platform@{__version__}",
            seed=task.seed,
            contamination_result=contamination,
        )
        repro.validate_complete()

        markdown = ReportRenderer().render_markdown(
            repro=repro,
            results=results,
            verdict=verdict,
            accuracy_before=accuracy_before,
            accuracy_after=accuracy_after,
        )
        markdown = f"{markdown}\n\n{self._effect_size_section(results)}"
        report_payload = redact(
            {
                "task_id": task.task_id,
                "content_hash": task.content_hash,
                "model_version": task.model_version,
                "baseline_model_version": task.params.get("baseline_model_version"),
                "dataset_version": repro.dataset_version,
                "dataset_sha": task.dataset_sha,
                "seed": task.seed,
                "verdict": verdict.tier.value,
                "blocking_ids": list(verdict.blocking_ids),
                "warning_ids": list(verdict.warning_ids),
                "covered_rule_count": verdict.covered_rule_count,
                "uncovered_rule_count": verdict.uncovered_rule_count,
                "uncovered_ratio": verdict.uncovered_ratio,
                "accuracy_before": accuracy_before,
                "accuracy_after": accuracy_after,
                "results": [r.model_dump(mode="json") for r in results],
                "reproducibility": repro.model_dump(mode="json"),
                "report_markdown": markdown,
            }
        )
        report_hash = store.save(report_payload)

        outcome = EvaluationOutcome(
            task_id=task.task_id,
            content_hash=task.content_hash,
            report_hash=report_hash,
            # Explicit snapshot step (D-3): the domain SafetyVerdict is a mutable
            # dataclass, so the outcome must hold the frozen GuardrailVerdict.
            verdict=GuardrailVerdict.from_domain_verdict(verdict),
            results=results,
            reproducibility=repro,
            accuracy_before=accuracy_before,
            accuracy_after=accuracy_after,
            report_markdown=markdown,
        )

        if ledger is not None:
            # The verdict and the report address are the audit-worthy facts. Deliberately
            # NOT the payload or the markdown: the ledger carries created_at, and nothing
            # time-derived may reach report_hash (design.md 4.1 reproducibility).
            # ``promotable`` is read off the outcome rather than recomputed, so the audit
            # trail cannot disagree with the artifact about what was promotable.
            ledger.append(
                "evaluation.completed",
                {
                    "task_id": outcome.task_id,
                    "content_hash": outcome.content_hash,
                    "report_hash": outcome.report_hash,
                    "verdict": outcome.verdict.tier.value,
                    "promotable": outcome.promotable,
                },
            )

        return outcome

    @staticmethod
    def _effect_size_section(results: Sequence[PairedResult]) -> str:
        """Effect size + 95% CI table.

        The upstream renderer shows p-values only (read-only contract, reported to the
        harness). Design §3 M003 F4 forbids presenting a p-value as the conclusion and
        §7 requires absolute lift + 95% CI alongside, so the pipeline appends them.
        """
        lines = [
            "## Effect size & 95% CI",
            "",
            (
                "| Metric | Tested quantity | abs lift | rel lift | 95% CI (abs lift) | p_raw | "
                "p_corrected (authoritative) | significant after correction |"
            ),
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in results:
            quantity = "paired predictions (label)" if r.method == "mcnemar" else "paired scores"
            # Correction is mandatory upstream (``assert_correction_applied`` ran in
            # ``paired_statistics``), so None is unreachable here; render it as n/a
            # rather than letting a comparison against None raise or, worse, reading as
            # "not significant".
            p_corr = r.p_corrected
            significant = "n/a" if p_corr is None else ("yes" if p_corr < ALPHA else "no")
            lines.append(
                f"| {r.test_name} | {quantity} | {r.abs_lift:.6g} | {r.rel_lift:.6g} | "
                f"[{r.ci_low:.6g}, {r.ci_high:.6g}] | {r.p_raw:.6g} | "
                f"{'n/a' if p_corr is None else format(p_corr, '.6g')} | {significant} |"
            )
        lines += [
            "",
            (
                "Accuracy before/after above is measured against the dataset ground truth label; "
                "the tested quantities in this table are the paired model outputs listed per row. "
                "Effect size and 95% CI are the decision basis — a p-value alone is never a "
                "conclusion (M003 F4)."
            ),
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _resolve_metrics(
        metrics: Sequence[MetricDefinition], registry: MetricRegistry
    ) -> list[MetricDefinition]:
        """Replace caller-supplied definitions with the registered ones.

        The registry is the authority (T-M7-13). Without this, a caller could introduce
        an id that was never registered, a version the catalogue never recorded, or a
        definition edited after registration, and the report would faithfully print
        whatever it was handed — so spec §3's "every report number maps to a registry id
        + version" was unenforceable. Fail closed, like an unevaluated redline.
        """
        resolved: list[MetricDefinition] = []
        for metric in metrics:
            try:
                registry.validate_metric_exists(metric.metric_id)
            except RegistryError as exc:
                raise EvaluationError(
                    f"metric {metric.metric_id!r} is not registered; a report number must "
                    f"map to a registry id (registered: {registry.list_ids()})"
                ) from exc
            history = registry.all_versions(metric.metric_id)
            if not 1 <= metric.version <= len(history):
                raise EvaluationError(
                    f"metric {metric.metric_id}@{metric.version} is not in the registry "
                    f"history (recorded versions: 1..{len(history)})"
                )
            resolved.append(history[metric.version - 1])
        return resolved

    @staticmethod
    def _check_runners(task: Task, baseline_runner: Any, candidate_runner: Any) -> None:
        """Bind the snapshot to the runners, so a report can never claim the wrong model."""
        expected_baseline = task.params.get("baseline_model_version")
        if expected_baseline is not None and expected_baseline != baseline_runner.model_version:
            raise EvaluationError(
                f"baseline runner {baseline_runner.model_version!r} does not match the task "
                f"snapshot baseline {expected_baseline!r}"
            )
        if candidate_runner.model_version != task.model_version:
            raise EvaluationError(
                f"candidate runner {candidate_runner.model_version!r} does not match the task "
                f"snapshot model {task.model_version!r}"
            )

    @staticmethod
    def _check_dataset(task: Task, dataset: Dataset) -> None:
        """Bind the snapshot to the data actually evaluated (§4.1: the report must answer
        "how was this scored"). A report that prints the snapshot's ``dataset_sha`` while
        scanning a different corpus is a claim it cannot back up."""
        actual_sha = dataset.sha256 or dataset.compute_sha()
        snapshot = (task.dataset_id, task.dataset_version, task.dataset_sha)
        actual = (dataset.dataset_id, dataset.version, actual_sha)
        if actual != snapshot:
            raise EvaluationError(
                f"evaluated dataset {actual[0]}@{actual[1]} (sha {actual[2][:12]}) does not "
                f"match the task snapshot {snapshot[0]}@{snapshot[1]} (sha {str(snapshot[2])[:12]})"
            )

    @staticmethod
    def _value(metric: MetricDefinition, prediction: dict) -> float:
        key = SUPPORTED_METRIC_KINDS.get(metric.kind)
        if key is None:
            supported = ", ".join(sorted(k.value for k in SUPPORTED_METRIC_KINDS))
            raise EvaluationError(
                f"metric {metric.metric_id} ({metric.kind.value}) cannot be evaluated from "
                f"the runner contract (score/label); supported kinds: {supported}"
            )
        if key not in prediction:
            raise EvaluationError(
                f"metric {metric.metric_id} ({metric.kind.value}) needs {key!r} in the prediction"
            )
        return float(prediction[key])

    @staticmethod
    def _accuracy(
        dataset: Dataset, pairs: Sequence[tuple[str, dict, dict]]
    ) -> tuple[float | None, float | None]:
        """Accuracy against ground truth; ``(None, None)`` when the dataset has no labels."""
        key = next((k for k in GROUND_TRUTH_KEYS if dataset.rows and k in dataset.rows[0]), None)
        if key is None:
            return None, None
        n = len(pairs)
        before = sum(
            1 for row, (_, b, _) in zip(dataset.rows, pairs, strict=True) if b["label"] == row[key]
        )
        after = sum(
            1 for row, (_, _, a) in zip(dataset.rows, pairs, strict=True) if a["label"] == row[key]
        )
        return before / n, after / n


__all__ = [
    "ALPHA",
    "CORRECTIONS",
    "SUPPORTED_METRIC_KINDS",
    "EvaluationError",
    "EvaluationPipeline",
    "UnalignedCases",
]
