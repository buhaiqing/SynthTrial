"""Interrupted Time Series (M10 T-M10-04)."""

from __future__ import annotations

import pandas as pd
import statsmodels.formula.api as smf


def interrupted_time_series(df: pd.DataFrame) -> dict:
    """df columns: time (numeric), outcome, intervention (0/1 post)."""
    required = {"time", "outcome", "intervention"}
    if not required.issubset(df.columns):
        raise ValueError(f"df must contain {sorted(required)}")
    d = df.copy()
    d["time_intervention"] = d["time"] * d["intervention"]
    model = smf.ols("outcome ~ time + intervention + time_intervention", data=d).fit()
    est = float(model.params["intervention"])
    se = float(model.bse["intervention"])
    p = float(model.pvalues["intervention"])
    return {"level_change": est, "se": se, "p_value": p, "ci_low": est - 1.96 * se, "ci_high": est + 1.96 * se}