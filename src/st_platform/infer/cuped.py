"""CUPED variance reduction for SynthTrial P0 (st-infer)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np


def _var(arr: np.ndarray) -> float:
    return float(np.var(arr, ddof=1)) if arr.size > 1 else float(np.var(arr, ddof=0))


def fit_theta(metric: Sequence[float], covariate: Sequence[float]) -> float:
    """Fit CUPED theta = Cov(metric, covariate) / Var(covariate).

    Raises ValueError if covariate variance is 0.
    """
    m = np.asarray(metric, dtype=float).ravel()
    x = np.asarray(covariate, dtype=float).ravel()
    if m.shape != x.shape:
        raise ValueError("metric and covariate must have same shape")
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
    """Adjusted metric: metric - theta*(covariate - mean(covariate))."""
    m = np.asarray(metric, dtype=float).ravel()
    x = np.asarray(covariate, dtype=float).ravel()
    if m.shape != x.shape:
        raise ValueError("metric and covariate must have same shape")
    vx = float(np.var(x, ddof=1)) if x.size > 1 else float(np.var(x, ddof=0))
    if vx == 0:
        raise ValueError("CUPED undefined: covariate variance is 0")
    adj = m - float(theta) * (x - np.mean(x))
    return adj


# Alias
adjust = cuped_adjust
fit = fit_theta
theta = fit_theta
