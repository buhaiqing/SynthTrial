"""Paired statistical tests for SynthTrial P0 (st-infer)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from scipy import stats

ArrayLike = Sequence[float]


def _to_array(x: Any) -> np.ndarray:
    return np.asarray(x, dtype=float)


def _extract_case_ids(
    kwargs: dict[str, Any],
) -> tuple[list[Any] | None, list[Any] | None, list[Any] | None]:
    """Collect before/after case-id sequences from optional kwargs.

    Accepts a wide variety of keyword names to be forgiving about caller
    naming, but never silently drops or reorders anything.
    """
    before_ids: list[Any] | None = None
    after_ids: list[Any] | None = None
    shared: list[Any] | None = None

    # Direct name variants.
    before_names = {
        "before_case_ids",
        "case_ids_before",
        "ids_before",
        "case_id_before",
        "before_ids",
    }
    after_names = {"after_case_ids", "case_ids_after", "ids_after", "case_id_after", "after_ids"}
    shared_names = {"case_ids", "case_id", "ids"}

    for k, v in kwargs.items():
        lk = k.lower()
        if lk in before_names or lk.endswith("_before") and ("case" in lk or "id" in lk):
            before_ids = list(v)
        elif lk in after_names or lk.endswith("_after") and ("case" in lk or "id" in lk):
            after_ids = list(v)
        elif lk in shared_names:
            shared = list(v)
        else:
            # Heuristic: any kwarg with "case" or "id" in name.
            if (
                ("case" in lk or lk.endswith("_ids") or lk == "ids")
                and before_ids is None
                and after_ids is None
                and shared is None
            ):
                shared = list(v)
    return before_ids, after_ids, shared


def _validate_inputs(
    before: ArrayLike,
    after: ArrayLike,
    **kwargs: Any,
) -> tuple[np.ndarray, np.ndarray]:
    b = _to_array(before)
    a = _to_array(after)
    if b.ndim != 1 or a.ndim != 1:
        raise ValueError("before and after must be 1-D arrays")
    if b.shape[0] != a.shape[0]:
        raise ValueError(f"length mismatch: before={b.shape[0]} vs after={a.shape[0]}")

    before_ids, after_ids, shared = _extract_case_ids(kwargs)

    if shared is not None and len(shared) != b.shape[0]:
        raise ValueError(f"case_ids length {len(shared)} != data length {b.shape[0]}")

    if before_ids is not None and len(before_ids) != b.shape[0]:
        raise ValueError(f"before case_ids length {len(before_ids)} != data length {b.shape[0]}")
    if after_ids is not None and len(after_ids) != a.shape[0]:
        raise ValueError(f"after case_ids length {len(after_ids)} != data length {a.shape[0]}")

    if before_ids is not None and after_ids is not None and before_ids != after_ids:
        raise ValueError("before and after are not aligned by case_id")

    # If shared ids given alongside per-side ids, shared must match order.
    if shared is not None and before_ids is not None and shared != before_ids:
        raise ValueError("before data not aligned with supplied case_ids")
    if shared is not None and after_ids is not None and shared != after_ids:
        raise ValueError("after data not aligned with supplied case_ids")

    return b, a


def paired_t_test(before, after, **kwargs):
    b, a = _validate_inputs(before, after, **kwargs)
    diff = a - b
    n = b.shape[0]

    # A t statistic needs >=2 pairs and non-zero spread in the differences.
    # scipy returns nan for both, and a nan rendered into a report reads as
    # "no result" -- indistinguishable from "no effect". Fail visibly instead.
    if n < 2:
        raise ValueError(f"paired t-test needs at least 2 pairs, got n={n}")
    sd = float(np.std(diff, ddof=1))
    if sd == 0.0:
        mean_diff = float(np.mean(diff))
        if mean_diff == 0.0:
            # Exact, reportable: the two models produced identical values.
            return {
                "test": "paired_t_test",
                "test_name": "paired_t",
                "n": int(n),
                "statistic": 0.0,
                "pvalue": 1.0,
                "p_value": 1.0,
                "p": 1.0,
                "mean_diff": mean_diff,
                "ci_low": 0.0,
                "ci_high": 0.0,
                "degenerate": "zero_variance_identical",
            }
        raise ValueError(
            "paired t-test undefined: every difference is the same non-zero "
            f"value ({mean_diff}); variance is 0 so the t statistic divides by zero"
        )

    res = stats.ttest_rel(b, a)
    mean_diff = float(np.mean(diff))
    se = sd / np.sqrt(n)
    # t-based 95% CI on mean difference.
    tcrit = float(stats.t.ppf(0.975, df=n - 1))
    ci_low = mean_diff - tcrit * se
    ci_high = mean_diff + tcrit * se
    out = {
        "test": "paired_t_test",
        "test_name": "paired_t",
        "n": int(n),
        "statistic": float(res.statistic),
        "pvalue": float(res.pvalue),
        "p_value": float(res.pvalue),
        "p": float(res.pvalue),
        "mean_diff": mean_diff,
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
    }
    return out


def wilcoxon_signed_rank(before, after, **kwargs):
    b, a = _validate_inputs(before, after, **kwargs)
    diff = a - b
    n = b.shape[0]
    if n < 2:
        raise ValueError(f"wilcoxon needs at least 2 pairs, got n={n}")
    if not np.any(diff):
        # scipy emits a RuntimeWarning ("invalid value in scalar divide") and
        # still returns p=1.0 here. Handle it explicitly so no warning escapes
        # and the caller gets an explicit, documented result.
        return {
            "test": "wilcoxon_signed_rank",
            "test_name": "wilcoxon",
            "n": int(n),
            "statistic": 0.0,
            "pvalue": 1.0,
            "p_value": 1.0,
            "p": 1.0,
            "median_diff": 0.0,
            "degenerate": "all_zero_differences",
        }
    res = stats.wilcoxon(b, a)
    out = {
        "test": "wilcoxon_signed_rank",
        "test_name": "wilcoxon",
        "n": int(n),
        "statistic": float(res.statistic),
        "pvalue": float(res.pvalue),
        "p_value": float(res.pvalue),
        "p": float(res.pvalue),
        "median_diff": float(np.median(diff)),
    }
    return out


def mcnemar(before_binary, after_binary, **kwargs):
    b = _to_array(before_binary)
    a = _to_array(after_binary)
    if b.ndim != 1 or a.ndim != 1:
        raise ValueError("inputs must be 1-D")
    if b.shape[0] != a.shape[0]:
        raise ValueError(f"length mismatch: before={b.shape[0]} vs after={a.shape[0]}")
    # validate via shared validator for case ids
    b, a = _validate_inputs(b.tolist(), a.tolist(), **kwargs)

    # binarize
    bb = (b != 0).astype(int)
    aa = (a != 0).astype(int)

    # contingency table: rows=before, cols=after
    n00 = int(np.sum((bb == 0) & (aa == 0)))
    n01 = int(np.sum((bb == 0) & (aa == 1)))
    n10 = int(np.sum((bb == 1) & (aa == 0)))
    n11 = int(np.sum((bb == 1) & (aa == 1)))
    table = [[n00, n01], [n10, n11]]

    n = b.shape[0]
    discordant = n01 + n10
    if discordant == 0:
        statistic = 0.0
        pvalue = 1.0
    else:
        statistic = ((n01 - n10) ** 2) / discordant
        pvalue = float(stats.chi2.sf(statistic, 1))
    out = {
        "test": "mcnemar",
        "test_name": "mcnemar",
        "n": int(n),
        "statistic": float(statistic),
        "pvalue": float(pvalue),
        "p_value": float(pvalue),
        "p": float(pvalue),
        "contingency": table,
        "n01": n01,
        "n10": n10,
    }
    return out
