"""Tests for DiD (M10)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from st_platform.causal.did import difference_in_differences, parallel_trends_test


def test_did_recovers_effect():
    # treated post +10
    rows = []
    for t in [0, 1]:
        for post in [0, 1]:
            for i in range(50):
                base = 5.0
                treat_effect = 10.0 if (t == 1 and post == 1) else 0.0
                rows.append({"outcome": base + treat_effect + np.random.default_rng(0).normal(0, 0.1), "treated": t, "post": post})
    df = pd.DataFrame(rows)
    res = difference_in_differences(df)
    assert 8.0 < res["estimate"] < 12.0


def test_parallel_trends():
    rng = np.random.default_rng(2)
    rows = []
    for t in [0, 1]:
        for time in range(5):
            for i in range(20):
                rows.append({"outcome": 2.0 * time + rng.normal(0, 0.5), "treated": t, "time": time})
    df = pd.DataFrame(rows)
    res = parallel_trends_test(df)
    assert res["parallel_trends_ok"] is True