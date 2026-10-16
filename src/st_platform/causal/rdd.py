"""Regression Discontinuity Design (M10 T-M10-04 subset)."""

from __future__ import annotations

import pandas as pd
import statsmodels.formula.api as smf


def regression_discontinuity(df: pd.DataFrame, cutoff: float = 0.0, bandwidth: float | None = None) -> dict:
    """Sharp RDD with local linear regression. df columns: x, y."""
    if not {"x", "y"}.issubset(df.columns):
        raise ValueError("df must contain x, y")
    d = df.copy()
    if bandwidth is not None:
        d = d[(d["x"] >= cutoff - bandwidth) & (d["x"] <= cutoff + bandwidth)]
    d["treated"] = (d["x"] >= cutoff).astype(int)
    d["xc"] = d["x"] - cutoff
    model = smf.ols("y ~ treated + xc + treated:xc", data=d).fit()
    est = float(model.params["treated"])
    se = float(model.bse["treated"])
    p = float(model.pvalues["treated"])
    return {"estimate": est, "se": se, "p_value": p, "ci_low": est - 1.96 * se, "ci_high": est + 1.96 * se, "n": len(d)}