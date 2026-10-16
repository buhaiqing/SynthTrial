"""Result container for paired tests (SynthTrial P0, st-infer)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class PairedResult(BaseModel):
    """Frozen, serializable paired-test result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    test_name: str
    n: int
    statistic: float
    p_raw: float
    p_corrected: float | None
    method: str
    ci_low: float
    ci_high: float
    abs_lift: float
    rel_lift: float
    correction_applied: str | None = None


def assert_correction_applied(results: Any) -> None:
    """Raise if any result has p_corrected None while >1 test was run."""
    if hasattr(results, "p_corrected") and not isinstance(results, (list, tuple, set)):
        seq = [results]
    else:
        try:
            seq = list(results)
        except TypeError:
            seq = [results]
    if not seq:
        return
    if len(seq) <= 1:
        return
    for r in seq:
        pc = getattr(r, "p_corrected", None)
        if isinstance(r, dict):
            pc = r.get("p_corrected")
        if pc is None:
            raise ValueError("correction must be applied when more than one test is run")
