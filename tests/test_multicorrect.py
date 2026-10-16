"""Tests for multiple comparison correction."""

import pytest
from statsmodels.stats.multitest import multipletests

from st_platform.infer.multicorrect import benjamini_hochberg, bonferroni, holm

PVALS = [0.01, 0.04, 0.03, 0.2]


def test_bonferroni_aligned():
    res = bonferroni(PVALS)
    exp = multipletests(PVALS, method="bonferroni")[1]
    assert res == pytest.approx(list(exp))


def test_holm_aligned():
    res = holm(PVALS)
    exp = multipletests(PVALS, method="holm")[1]
    assert res == pytest.approx(list(exp))


def test_bh_aligned():
    res = benjamini_hochberg(PVALS)
    exp = multipletests(PVALS, method="fdr_bh")[1]
    assert res == pytest.approx(list(exp))


def test_empty():
    assert bonferroni([]) == []
    assert holm([]) == []
    assert benjamini_hochberg([]) == []


def test_order_preserved():
    pvals = [0.5, 0.01]
    res = bonferroni(pvals)
    # second should be 0.02
    assert res[1] == pytest.approx(0.02)
    assert res[0] == pytest.approx(1.0)
