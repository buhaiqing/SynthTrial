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
        raise ValueError(f"mean CI needs at least 2 observations, got n={n}")
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
        raise ValueError(
            f"absolute lift CI needs at least 2 pairs, got n={n}; "
            "a point interval would read as certainty we do not have"
        )
    m = float(np.mean(diff))
    se = float(np.std(diff, ddof=1) / np.sqrt(n))
    tcrit = float(stats.t.ppf(1 - alpha / 2, df=n - 1))
    return (m - tcrit * se, m + tcrit * se)


def relative_lift_ci95(before, after, alpha: float = 0.05) -> tuple[float, float]:
    """95% CI for relative lift = (mean(after) - mean(before)) / mean(before).

    Uses the delta method. ``before_mean`` is a *sampled* mean carrying its own
    variance, so dividing the absolute-difference CI by it understates
    uncertainty. The error is one-directional (always too narrow) and explodes
    as the baseline rate approaches zero -- exactly the rare-adverse-event case
    where a too-narrow interval reads as "no meaningful harm" when the honest
    interval cannot rule it out.

    Denominator variance is therefore propagated analytically.
    """
    b = np.asarray(before, dtype=float).ravel()
    a = np.asarray(after, dtype=float).ravel()
    if b.shape != a.shape:
        raise ValueError("before and after must have same shape")

    n = b.size
    b_bar = float(b.mean())
    if b_bar == 0:
        raise ValueError("relative_lift_ci undefined when before_mean == 0")

    a_bar = float(a.mean())
    point = (a_bar - b_bar) / b_bar
    if n < 2:
        raise ValueError(
            f"relative lift CI needs at least 2 pairs, got n={n}; "
            "a point interval would read as certainty we do not have"
        )

    var_a = float(a.var(ddof=1)) / n
    var_b = float(b.var(ddof=1)) / n
    cov_ab = float(np.cov(a, b, ddof=1)[0, 1]) / n

    # Var((a_bar - b_bar)/b_bar) via gradient of R w.r.t. (a_bar, b_bar)
    radicand = var_a / (b_bar**2) + (a_bar**2 / b_bar**4) * var_b - 2 * (a_bar / b_bar**3) * cov_ab
    if radicand < 0:
        # Only floating-point noise can push this negative; clamp, don't raise.
        radicand = 0.0
    se = float(np.sqrt(radicand))
    tcrit = float(stats.t.ppf(1 - alpha / 2, df=n - 1))
    return (float(point - tcrit * se), float(point + tcrit * se))
