"""Multiple-comparison correction for SynthTrial P0 (st-infer)."""

from __future__ import annotations

from collections.abc import Iterable

from statsmodels.stats.multitest import multipletests


def _to_list(pvalues: Iterable[float]) -> list[float]:
    return [float(p) for p in pvalues]


def bonferroni(pvalues: Iterable[float]) -> list[float]:
    """Bonferroni correction. Returns adjusted p-values aligned to input."""
    pv = _to_list(pvalues)
    if not pv:
        return []
    _, adj, _, _ = multipletests(pv, method="bonferroni")
    return [float(x) for x in adj]


def holm(pvalues: Iterable[float]) -> list[float]:
    """Holm-Bonferroni correction. Returns adjusted p-values aligned to input."""
    pv = _to_list(pvalues)
    if not pv:
        return []
    _, adj, _, _ = multipletests(pv, method="holm")
    return [float(x) for x in adj]


def benjamini_hochberg(pvalues: Iterable[float]) -> list[float]:
    """Benjamini-Hochberg FDR correction. Returns adjusted p-values aligned to input."""
    pv = _to_list(pvalues)
    if not pv:
        return []
    _, adj, _, _ = multipletests(pv, method="fdr_bh")
    return [float(x) for x in adj]


# Aliases
bh = benjamini_hochberg
bh_correction = benjamini_hochberg
bonf = bonferroni
holm_bonferroni = holm
fdr_bh = benjamini_hochberg
