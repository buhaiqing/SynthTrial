"""Effect size / lift helpers for SynthTrial P0 (st-infer)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from scipy import stats


def absolute_lift(before_mean: float, after_mean: float) -> float:
    """Absolute lift: after - before."""
    return float(after_mean) - float(before_mean)


def relative_lift(before_mean: float, after_mean: float) -> float:
    """Relative lift: (after - before) / before. Raises if before_mean == 0."""
    bm = float(before_mean)
    if bm == 0:
        raise ValueError("relative_lift undefined when before_mean == 0")
    return (float(after_mean) - bm) / bm


def _mean_ci(arr: Sequence[float], alpha: float = 0.05) -> tuple[float, float]:
    a = np.asarray(arr, dtype=float).ravel()
    n = a.size
    if n < 2:
        m = float(np.mean(a)) if n else float("nan")
        return (m, m)
    m = float(np.mean(a))
    se = float(np.std(a, ddof=1) / np.sqrt(n))
    tcrit = float(stats.t.ppf(1 - alpha / 2, df=n - 1))
    return (m - tcrit * se, m + tcrit * se)


def ci95(values: Any, alpha: float = 0.05) -> tuple[float, float]:
    """95% CI (default) on the mean of ``values``."""
    return _mean_ci(values, alpha)


def absolute_lift_ci95(before, after, alpha: float = 0.05) -> tuple[float, float]:
    """95% CI on the paired (after - before) mean difference."""
    b = np.asarray(before, dtype=float).ravel()
    a = np.asarray(after, dtype=float).ravel()
    if b.shape != a.shape:
        raise ValueError("before and after must have same shape")
    diff = a - b
    n = diff.size
    if n < 2:
        m = float(np.mean(diff)) if n else float("nan")
        return (m, m)
    m = float(np.mean(diff))
    se = float(np.std(diff, ddof=1) / np.sqrt(n))
    tcrit = float(stats.t.ppf(1 - alpha / 2, df=n - 1))
    return (m - tcrit * se, m + tcrit * se)


def relative_lift_ci95(before, after, alpha: float = 0.05) -> tuple[float, float]:
    """95% CI on relative lift = abs_lift_ci / before_mean."""
    before_mean = float(np.mean(np.asarray(before, dtype=float)))
    if before_mean == 0:
        raise ValueError("relative_lift_ci undefined when before_mean == 0")
    lo, hi = absolute_lift_ci95(before, after, alpha)
    ci_lo = lo / before_mean
    ci_hi = hi / before_mean
    if ci_lo > ci_hi:
        ci_lo, ci_hi = ci_hi, ci_lo
    return (float(ci_lo), float(ci_hi))


# Aliases to maximize naming compatibility.
ci95_absolute = absolute_lift_ci95
ci95_relative = relative_lift_ci95
abs_lift_ci95 = absolute_lift_ci95
rel_lift_ci95 = relative_lift_ci95
ci95_abs = absolute_lift_ci95
ci95_rel = relative_lift_ci95
ci95_mean = ci95
# Functional-ish names.
absolute_ci95 = absolute_lift_ci95
relative_ci95 = relative_lift_ci95
