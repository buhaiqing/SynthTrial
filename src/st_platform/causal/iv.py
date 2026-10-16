"""Instrumental Variables / 2SLS (M10 T-M10-04)."""

from __future__ import annotations



def two_sls(y, X, Z):
    """y: (n,), X: (n,k) endogenous regressors, Z: (n,l) instruments (l>=k). Returns beta."""
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    Z = np.asarray(Z, float)
    # first stage: X_hat = Z (Z'Z)^-1 Z'X
    ZtZ_inv = np.linalg.pinv(Z.T @ Z)
    X_hat = Z @ ZtZ_inv @ (Z.T @ X)
    # second stage
    beta = np.linalg.pinv(X_hat.T @ X_hat) @ (X_hat.T @ y)
    return beta.tolist()