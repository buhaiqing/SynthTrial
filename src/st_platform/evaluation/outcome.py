"""EvaluationOutcome: the frozen artifact of one offline evaluation (P0 vertical slice).

Guardrail and effectiveness never merge into a single score (design §4.2): ``verdict``
carries the safety tier, the paired statistics live in ``results`` / ``accuracy_*``.
``promotable`` is derived from the guardrail alone.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field, model_validator

from st_platform.common.types import SafetyVerdictTier, Versioned
from st_platform.infer.result import PairedResult
from st_platform.report.report import ReproducibilityMeta


class GuardrailVerdict(Versioned):
    """Immutable snapshot of st-safety's ``SafetyVerdict`` inside an outcome.

    ``SafetyVerdict`` is a mutable stdlib dataclass, so holding it directly would let a
    caller rewrite ``outcome.verdict.tier`` after the fact -- verified: the outer
    pydantic ``frozen=True`` does not stop a mutation of the object it wraps, so a BLOCK
    could be flipped to PASS in memory (violates D-3: a finished result is not
    overwritable). Lists become tuples and evidence is kept as canonical JSON, so no
    mutable container survives inside the frozen artifact.
    """

    tier: SafetyVerdictTier
    blocking_ids: tuple[str, ...] = ()
    warning_ids: tuple[str, ...] = ()
    fired_ids: tuple[str, ...] = ()
    passing_ids: tuple[str, ...] = ()
    covered_rule_count: int = 0
    uncovered_rule_count: int = 0
    uncovered_ratio: float = 0.0
    #: ``json.dumps`` of the domain verdict's evidence, for a stable, hashable record.
    evidence_json: str = "{}"

    @staticmethod
    def _domain_verdict_fields(v: Any) -> dict[str, Any]:
        """Field mapping for a mutable ``st_safety.checker.SafetyVerdict``."""
        return {
            "tier": v.tier,
            "blocking_ids": tuple(v.blocking_ids),
            "warning_ids": tuple(v.warning_ids),
            "fired_ids": tuple(v.fired_ids),
            "passing_ids": tuple(v.passing_ids),
            "covered_rule_count": v.covered_rule_count,
            "uncovered_rule_count": v.uncovered_rule_count,
            "uncovered_ratio": v.uncovered_ratio,
            "evidence_json": json.dumps(v.evidence, sort_keys=True, default=str),
        }

    @classmethod
    def from_domain_verdict(cls, verdict: Any) -> GuardrailVerdict:
        """Snapshot a domain verdict into the frozen artifact (D-3).

        Named so the call site states this step. Relying on pydantic's implicit
        ``before`` validator hid the immutability conversion from readers and hid the
        ``SafetyVerdict`` -> ``GuardrailVerdict`` assignment from the type checker.
        """
        return cls.model_validate(cls._domain_verdict_fields(verdict))

    @model_validator(mode="before")
    @classmethod
    def _coerce_domain_verdict(cls, data: Any) -> Any:
        if hasattr(data, "tier"):  # a st_safety.checker.SafetyVerdict
            return cls._domain_verdict_fields(data)
        return data


class EvaluationOutcome(Versioned):
    """Frozen result of ``EvaluationPipeline.run``.

    Immutability scope (D-3): attribute rebinding is refused (pydantic ``frozen``),
    ``verdict`` is a :class:`GuardrailVerdict` snapshot and ``reproducibility.contamination_result``
    is deep-frozen. Residual risk, by contract: ``results`` is declared ``list[PairedResult]``
    per the slice spec, so the list container itself stays mutable.

    Addressing: ``content_hash`` is the **task snapshot** hash (identical task => identical
    content_hash, regardless of metrics/redlines/correction); ``report_hash`` is the
    content address of this specific evaluation's persisted payload. Cache per-run
    results on ``report_hash``, not on ``content_hash``.
    """

    task_id: str
    #: Task snapshot hash (identical snapshot => identical hash; metrics/redlines are
    #: NOT part of it -- see the class docstring).
    content_hash: str
    #: ReportStore address of the persisted report payload (same evaluation inputs =>
    #: same hash). This is the per-evaluation address; see the class docstring.
    report_hash: str
    #: Guardrail verdict -- kept apart from the effectiveness numbers below.
    verdict: GuardrailVerdict
    results: list[PairedResult] = Field(default_factory=list)
    reproducibility: ReproducibilityMeta
    accuracy_before: float | None = None
    accuracy_after: float | None = None
    report_markdown: str = ""

    @property
    def promotable(self) -> bool:
        """``True`` only for a PASS guardrail verdict (design §4.2, AGENTS §7 D-6).

        ``WARN`` is **not** an automatic yes: it means a human approver must decide, so
        it is not promotable by this pipeline. ``BLOCK`` is a one-vote veto regardless of
        what the effectiveness numbers say.
        """
        return self.verdict.tier == SafetyVerdictTier.PASS

    def effectiveness(self) -> dict[str, Any]:
        """Effectiveness numbers only -- deliberately excluding the guardrail verdict."""
        return {
            "results": [r.model_dump(mode="json") for r in self.results],
            "accuracy_before": self.accuracy_before,
            "accuracy_after": self.accuracy_after,
        }


__all__ = ["EvaluationOutcome", "GuardrailVerdict"]
