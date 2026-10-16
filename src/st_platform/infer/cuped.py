"""CUPED variance reduction for SynthTrial P0 (st-infer)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np


def assert_pre_treatment_covariate(covariate: Sequence[float], metric: Sequence[float]) -> None:
    """Reject a covariate that is the metric itself: CUPED leakage.

    A CUPED covariate must be measured BEFORE treatment -- the same unit's
    previous score, a prior visit's proxy value, anything that cannot have been
    produced by the treatment under test.

    Why this guard exists: the adjustment is metric - theta*(covariate - mean).
    If the covariate *is* the post-treatment metric, the adjustment subtracts
    the outcome from itself, residual variance collapses for any theta, and a
    difference that is pure noise can be reported as significant. The result is
    then indistinguishable from a genuine variance reduction -- nothing
    downstream can detect it. Cheap check here, unfalsifiable claim avoided.

    Raises ValueError when covariate and metric hold identical values (or are
    the same array object). Different-but-correlated series are allowed: that
    is what a real pre-period proxy looks like.
    """
    x = np.asarray(covariate, dtype=float).ravel()
    m = np.asarray(metric, dtype=float).ravel()
    if x.size > 0 and x.size == m.size and (x is m or bool(np.array_equal(x, m, equal_nan=True))):
        raise ValueError(
            "CUPED covariate leakage: covariate is identical to the metric; "
            "the covariate must be measured before treatment"
        )


def fit_theta(metric: Sequence[float], covariate: Sequence[float]) -> float:
    """Fit CUPED theta = Cov(metric, covariate) / Var(covariate).

    The covariate must be measured BEFORE treatment: see
    `assert_pre_treatment_covariate` for why an identical series is rejected
    instead of silently deflating the variance.

    Raises ValueError if the shapes differ, if the covariate is the metric
    itself, or if covariate variance is 0.
    """
    m = np.asarray(metric, dtype=float).ravel()
    x = np.asarray(covariate, dtype=float).ravel()
    if m.shape != x.shape:
        raise ValueError("metric and covariate must have same shape")
    assert_pre_treatment_covariate(covariate, metric)
    vx = float(np.var(x, ddof=1)) if x.size > 1 else float(np.var(x, ddof=0))
    if vx == 0:
        raise ValueError("CUPED undefined: covariate variance is 0")
    cov = float(np.cov(m, x, ddof=1)[0, 1])
    return cov / vx


def cuped_adjust(
    metric: Sequence[float],
    covariate: Sequence[float],
    theta: float,
) -> Any:
    """Adjusted metric: metric - theta*(covariate - mean(covariate)).

    Same pre-treatment requirement as `fit_theta`: an identical metric /
    covariate pair is rejected rather than adjusted, because that adjustment
    would erase the outcome's own variance (see
    `assert_pre_treatment_covariate`).
    """
    m = np.asarray(metric, dtype=float).ravel()
    x = np.asarray(covariate, dtype=float).ravel()
    if m.shape != x.shape:
        raise ValueError("metric and covariate must have same shape")
    assert_pre_treatment_covariate(covariate, metric)
    vx = float(np.var(x, ddof=1)) if x.size > 1 else float(np.var(x, ddof=0))
    if vx == 0:
        raise ValueError("CUPED undefined: covariate variance is 0")
    adj = m - float(theta) * (x - np.mean(x))
    return adj


# Alias
adjust = cuped_adjust
fit = fit_theta
theta = fit_theta
