"""Difference-in-Differences (M10 T-M10-02)."""

from __future__ import annotations

import pandas as pd
import statsmodels.formula.api as smf


def difference_in_differences(df: pd.DataFrame) -> dict:
    """2x2 DiD. df columns: outcome, treated (0/1), post (0/1)."""
    required = {"outcome", "treated", "post"}
    if not required.issubset(df.columns):
        raise ValueError(f"df must contain {sorted(required)}")
    model = smf.ols("outcome ~ treated * post", data=df).fit()
    # interaction term name
    key = "treated:post"
    if key not in model.params:
        key = "post:treated"
    est = float(model.params[key])
    se = float(model.bse[key])
    p = float(model.pvalues[key])
    ci_low = est - 1.96 * se
    ci_high = est + 1.96 * se
    return {"estimate": est, "se": se, "p_value": p, "ci_low": ci_low, "ci_high": ci_high, "n": len(df)}


def parallel_trends_test(panel: pd.DataFrame) -> dict:
    """Test parallel pre-trends. panel columns: outcome, treated (0/1), time (numeric). Pre-period only."""
    required = {"outcome", "treated", "time"}
    if not required.issubset(panel.columns):
        raise ValueError(f"panel must contain {sorted(required)}")
    df = panel.copy()
    df["treated_time"] = df["treated"] * df["time"]
    model = smf.ols("outcome ~ treated + time + treated_time", data=df).fit()
    key = "treated_time"
    est = float(model.params[key])
    se = float(model.bse[key])
    p = float(model.pvalues[key])
    return {"interaction_estimate": est, "se": se, "p_value": p, "parallel_trends_ok": p > 0.05}