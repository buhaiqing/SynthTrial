"""Tests for RDD (M10)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from st_platform.causal.rdd import regression_discontinuity


def test_rdd_recovers_jump():
    rng = np.random.default_rng(1)
    x = rng.uniform(-1, 1, 500)
    y = 2 * x + (x >= 0) * 3.0 + rng.normal(0, 0.1, 500)
    df = pd.DataFrame({"x": x, "y": y})
    res = regression_discontinuity(df, cutoff=0.0)
    assert 2.5 < res["estimate"] < 3.5