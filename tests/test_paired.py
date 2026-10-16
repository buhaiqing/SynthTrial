"""Tests for paired statistics."""

import pytest
from scipy import stats

from st_platform.infer.paired import mcnemar, paired_t_test, wilcoxon_signed_rank


def test_paired_t_known():
    before = [10.0, 12, 14, 16, 18]
    after = [11.0, 13, 13, 17, 20]
    exp = stats.ttest_rel(before, after)
    res = paired_t_test(before, after)
    assert res["n"] == 5
    assert res["statistic"] == pytest.approx(float(exp.statistic))
    assert res["pvalue"] == pytest.approx(float(exp.pvalue))
    # CI present
    assert res["ci_low"] < res["ci_high"]


def test_wilcoxon_known():
    before = [10.0, 12, 14, 16, 18]
    after = [11.0, 13, 13, 17, 20]
    exp = stats.wilcoxon(before, after)
    res = wilcoxon_signed_rank(before, after)
    assert res["n"] == 5
    assert res["statistic"] == pytest.approx(float(exp.statistic))
    assert res["pvalue"] == pytest.approx(float(exp.pvalue))


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        paired_t_test([1.0, 2], [1.0])


def test_case_id_mismatch_raises():
    with pytest.raises(ValueError):
        paired_t_test(
            [1.0, 2, 3],
            [2.0, 3, 4],
            before_case_ids=["a", "b", "c"],
            after_case_ids=["a", "b", "d"],
        )


def test_case_ids_length_mismatch_raises():
    with pytest.raises(ValueError):
        paired_t_test([1.0, 2, 3], [2.0, 3, 4], case_ids=["a", "b"])


def test_shared_case_ids_aligned():
    res = paired_t_test([1.0, 2, 3], [2.0, 3, 4], case_ids=["a", "b", "c"])
    assert res["n"] == 3


def test_mcnemar_known():
    before = [0, 0, 0, 1, 1, 1, 1, 1]
    after = [1, 1, 1, 0, 0, 1, 1, 1]
    res = mcnemar(before, after)
    # n01=3 (0->1), n10=2 (1->0)
    assert res["n01"] == 3
    assert res["n10"] == 2
    discordant = 5
    expected_stat = (3 - 2) ** 2 / discordant
    assert res["statistic"] == pytest.approx(expected_stat)
    from scipy.stats import chi2

    assert res["pvalue"] == pytest.approx(float(chi2.sf(expected_stat, 1)))


def test_mcnemar_length_mismatch_raises():
    with pytest.raises(ValueError):
        mcnemar([0, 1], [1])


def test_mcnemar_case_id_mismatch_raises():
    with pytest.raises(ValueError):
        mcnemar([0, 1, 0], [1, 0, 1], before_case_ids=["a", "b", "c"], after_case_ids=["a", "b", "d"])
