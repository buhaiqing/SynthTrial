"""Tests for causal/iv.py two_sls (M10 T-M10-04)."""

from __future__ import annotations

import numpy as np
import pytest

from st_platform.causal.iv import two_sls


def test_two_sls_runs_on_endogenous_dgp() -> None:
    rng = np.random.default_rng(0)
    n = 200
    Z = rng.normal(size=(n, 1))
    u = rng.normal(size=(n,))
    X = 0.5 * Z[:, 0] + u
    y = 2.0 * X + rng.normal(size=(n,))
    Zm = np.column_stack([np.ones(n), Z])
    Xm = np.column_stack([np.ones(n), X])
    beta = two_sls(y, Xm, Zm)
    assert isinstance(beta, list)
    assert len(beta) == 2
    assert all(np.isfinite(b) for b in beta)


def test_two_sls_recovers_exact_linear_beta() -> None:
    rng = np.random.default_rng(42)
    n = 500
    Z = rng.normal(size=(n, 1))
    X = 1.0 + 2.0 * Z[:, 0]
    y = 3.0 + 4.0 * X
    Zm = np.column_stack([np.ones(n), Z])
    Xm = np.column_stack([np.ones(n), X])
    beta = two_sls(y, Xm, Zm)
    assert beta[0] == pytest.approx(3.0, abs=1e-9)
    assert beta[1] == pytest.approx(4.0, abs=1e-9)
