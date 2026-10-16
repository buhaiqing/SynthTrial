"""Propensity Score Matching (M10 T-M10-04 subset)."""

from __future__ import annotations

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler


def propensity_score_match(
    treated: pd.DataFrame, control: pd.DataFrame, covariates: list[str]
) -> pd.DataFrame:
    """Return matched control rows (nearest neighbor on propensity score)."""
    t = treated.copy()
    c = control.copy()
    t["_treated"] = 1
    c["_treated"] = 0
    all_df = pd.concat([t, c], ignore_index=True)
    X = all_df[covariates].astype(float).to_numpy()
    y = all_df["_treated"].to_numpy()
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = LogisticRegression(max_iter=1000)
    model.fit(Xs, y)
    ps = model.predict_proba(Xs)[:, 1]
    all_df["_ps"] = ps
    treated_ps = all_df[all_df["_treated"] == 1]["_ps"].to_numpy()
    control_pool = all_df[all_df["_treated"] == 0].copy()
    matched_idx = []
    for p in treated_ps:
        j = (control_pool["_ps"] - p).abs().idxmin()
        matched_idx.append(j)
        control_pool = control_pool.drop(j)
    matched = all_df.loc[matched_idx].copy()
    return matched.drop(columns=["_treated", "_ps"])