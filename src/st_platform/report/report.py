"""Report rendering + reproducibility metadata (st-safety/st-ledger view)."""

from __future__ import annotations

from typing import Any

from st_platform.common.types import Versioned
from st_platform.safety.coverage import CoverageReport
from st_platform.config import kappa_threshold as _config_kappa_threshold


class ReportError(ValueError):
    """Report cannot be produced (e.g. missing reproducibility element)."""


ReproducibilityError = ReportError
ReproducibilityMetaError = ReportError


class ReproducibilityMeta(Versioned):
    model_version: str | None = None
    dataset_version: str | None = None
    dataset_sha: str | None = None
    code_version: str | None = None
    seed: Any = None
    contamination_result: Any = None

    def _is_empty(self, v: Any) -> bool:
        if v is None:
            return True
        if isinstance(v, str):
            return v.strip() == ""
        if isinstance(v, (list, tuple, set, dict)):
            return len(v) == 0
        return False

    def validate_complete(self) -> None:
        required = ["model_version", "dataset_version", "dataset_sha", "code_version", "seed"]
        missing = [f for f in required if self._is_empty(getattr(self, f))]
        # design.md §4.1 makes the contamination conclusion the fifth element.
        # Requiring the field to be non-empty is not enough: only the shape
        # contamination_detect() emits shows that a check actually ran, so a
        # hand-written placeholder cannot stand in for "we checked".
        # ``train_corpus_supplied`` is part of that shape: without it a report cannot
        # tell "checked, nothing overlapped" from "never checked" (T-M7-11).
        cr = self.contamination_result
        keys = {
            "train_corpus_supplied",
            "eval_count",
            "train_overlap_count",
            "overlap_ratio",
            "contaminated",
            "overlap_signatures",
        }
        if not (isinstance(cr, dict) and keys <= cr.keys()):
            missing.append("contamination_result")
        if missing:
            raise ReportError(f"missing required reproducibility elements: {missing}")

    def to_block(self) -> str:
        contamination = self.contamination_result
        if isinstance(contamination, dict):
            cont_str = ", ".join(f"{k}={v}" for k, v in contamination.items())
        else:
            cont_str = str(contamination) if contamination is not None else "n/a"
        lines = [
            "## Reproducibility",
            f"- model_version: {self.model_version}",
            f"- dataset_version: {self.dataset_version}",
            f"- dataset_sha: {self.dataset_sha}",
            f"- code_version: {self.code_version}",
            f"- seed: {self.seed}",
            f"- contamination_result: {cont_str}",
        ]
        return "\n".join(lines)


DEFAULT_KAPPA_THRESHOLD = 0.6


class ReportRenderer:
    """Renders a markdown report from evaluation artifacts."""

    def render_markdown(self, *args, **kwargs) -> str:
        # resolve reproducibility meta
        repro = (
            kwargs.get("repro")
            or kwargs.get("reproducibility")
            or kwargs.get("reproducibility_meta")
            or kwargs.get("meta")
            or kwargs.get("repro_meta")
        )
        if repro is None and len(args) >= 1 and not isinstance(args[0], (list, tuple, dict)):
            repro = args[0]
        if repro is None:
            raise ReportError("missing ReproducibilityMeta; cannot render report")
        # validate
        validator = getattr(repro, "validate_complete", None)
        if callable(validator):
            validator()

        # resolve paired results
        results = (
            kwargs.get("results")
            or kwargs.get("paired_results")
            or kwargs.get("stats")
            or kwargs.get("statistics")
            or kwargs.get("paired_results_list")
        )
        if results is None:
            results = []
        # resolve verdict
        verdict = (
            kwargs.get("verdict")
            or kwargs.get("safety_verdict")
            or kwargs.get("guardrail_verdict")
            or kwargs.get("safety")
        )

        acc_before = kwargs.get("accuracy_before", kwargs.get("acc_before"))
        acc_after = kwargs.get("accuracy_after", kwargs.get("acc_after"))

        # low-kappa subsets
        kappa_threshold = kwargs.get(
            "kappa_threshold",
            kwargs.get("low_kappa_threshold", _config_kappa_threshold()),
        )
        low_kappa_subsets = (
            kwargs.get("low_kappa_subsets")
            or kwargs.get("kappa_subsets")
            or kwargs.get("subsets")
            or kwargs.get("low_kappa")
            or []
        )
        # also derive from datasets/annotation kwargs
        extra_subsets = kwargs.get("datasets")
        if extra_subsets and isinstance(extra_subsets, (list, tuple)):
            low_kappa_subsets = list(low_kappa_subsets) + list(extra_subsets)

        # normalize low-kappa subsets
        low_flagged = []
        for s in low_kappa_subsets or []:
            name = None
            kappa = None
            if isinstance(s, dict):
                name = s.get("name") or s.get("id") or s.get("subset")
                kappa = s.get("kappa") or s.get("annotation_kappa")
            else:
                name = getattr(s, "name", None) or getattr(s, "id", None) or str(s)
                # try nested annotation
                if kappa is None:
                    kappa = getattr(s, "kappa", None)
                ann = getattr(s, "annotation", None)
                if kappa is None and ann is not None:
                    kappa = getattr(ann, "kappa", None)
                if isinstance(ann, dict):
                    kappa = kappa or ann.get("kappa")
            try:
                kappa = float(kappa) if kappa is not None else None
            except (TypeError, ValueError):
                kappa = None
            if kappa is None or kappa < kappa_threshold:
                low_flagged.append((name, kappa))

        # build markdown
        lines: list[str] = []
        title = kwargs.get("title", "Evaluation Report")
        lines.append(f"# {title}")
        lines.append("")

        # guardrail verdict section (separate from effectiveness)
        lines.append("## Guardrail verdict")
        if verdict is not None:
            tier = getattr(verdict, "tier", verdict)
            tier_val = getattr(tier, "value", tier)
            lines.append(f"- Verdict: {tier_val}")
            blocking = getattr(verdict, "blocking_ids", [])
            warning = getattr(verdict, "warning_ids", [])
            if blocking:
                lines.append(f"- Blocking: {', '.join(str(b) for b in blocking)}")
            if warning:
                lines.append(f"- Warning: {', '.join(str(w) for w in warning)}")
            lines.append(f"- Covered rules: {getattr(verdict, 'covered_rule_count', 0)}")
            lines.append(f"- Uncovered rules: {getattr(verdict, 'uncovered_rule_count', 0)}")
            lines.append(f"- Uncovered ratio: {getattr(verdict, 'uncovered_ratio', 0.0)}")
        else:
            lines.append("- Verdict: n/a")
        lines.append("")

        # effectiveness section
        lines.append("## Effectiveness")
        if acc_before is not None:
            lines.append(f"- Accuracy before: {acc_before}")
        if acc_after is not None:
            lines.append(f"- Accuracy after: {acc_after}")
        lines.append("")
        lines.append("### Statistical results")
        lines.append("| Test | p_raw | p_corrected (authoritative after correction) |")
        lines.append("|---|---|---|")
        for r in results or []:
            if isinstance(r, dict):
                name = r.get("test_name", r.get("metric", r.get("name", "")))
                p_raw = r.get("p_raw", r.get("p_raw", r.get("p_value")))
                p_corr = r.get("p_corrected", r.get("p_corrected", r.get("p_adjusted")))
            else:
                name = getattr(r, "test_name", getattr(r, "metric", getattr(r, "name", "")))
                p_raw = getattr(r, "p_raw", getattr(r, "p_value", None))
                p_corr = getattr(r, "p_corrected", getattr(r, "p_adjusted", None))
            lines.append(f"| {name} | {p_raw} | {p_corr} |")
        lines.append("")

        # low-kappa subsets
        if low_flagged:
            lines.append("## Annotation quality (low κ)")
            for name, kappa in low_flagged:
                lines.append(f"- {name} (κ={kappa})：结论仅供参考")
            lines.append("")

        # reproducibility
        lines.append(repro.to_block())
        lines.append("")

        # coverage if provided
        cov = kwargs.get("coverage") or kwargs.get("coverage_report")
        if isinstance(cov, CoverageReport):
            lines.append("## Coverage")
            lines.append(f"- Registered: {len(cov.registered_rule_ids)}")
            lines.append(f"- Evaluated: {len(cov.evaluated_rule_ids)}")
            lines.append(f"- Covered: {cov.covered_rule_count}")
            lines.append(f"- Uncovered: {cov.uncovered_rule_count}")
            lines.append(f"- Uncovered ratio: {cov.uncovered_ratio}")
            lines.append(f"- Coverage ratio: {cov.coverage_ratio}")
            lines.append(f"- Recall (known risks): {cov.recall()}")
            lines.append("")

        return "\n".join(lines)

    # compatibility aliases
    def render(self, *args, **kwargs) -> str:
        return self.render_markdown(*args, **kwargs)

    # allow method-style naming used elsewhere
    renderMarkdown = render_markdown


__all__ = ["ReportError", "ReportRenderer", "ReproducibilityError", "ReproducibilityMeta"]
