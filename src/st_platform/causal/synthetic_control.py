"""Synthetic Control (M10 T-M10-03)."""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize


def synthetic_control(
    treated_pre: np.ndarray,
    donor_pre: np.ndarray,
    treated_post: np.ndarray,
    donor_post: np.ndarray,
) -> dict:
    J = donor_pre.shape[1]

    def loss(w):
        synth = donor_pre @ w
        return float(np.sum((treated_pre - synth) ** 2))

    bnds = [(0, 1)] * J
    constraints = [{"type": "eq", "fun": lambda w: float(np.sum(w) - 1)}]
    w0 = np.ones(J) / J
    res = minimize(loss, w0, bounds=bnds, constraints=constraints, method="SLSQP")
    w = res.x
    synth_post = donor_post @ w
    effect = float(np.mean(treated_post - synth_post))
    return {"weights": w.tolist(), "effect": effect, "synthetic_post": synth_post.tolist()}