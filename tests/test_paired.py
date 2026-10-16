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
    # Real variation in the differences: a constant +1 shift is the degenerate
    # zero-variance case, which correctly raises rather than returning NaN.
    res = paired_t_test([1.0, 2, 3, 4], [2.0, 3, 5, 4], case_ids=["a", "b", "c", "d"])
    assert res["n"] == 4


def test_shared_case_ids_rejects_misaligned_ids():
    with pytest.raises(ValueError):
        paired_t_test([1.0, 2, 3], [2.0, 3, 4], case_ids=["a", "b"])


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


# --- Degenerate inputs must fail loud, never NaN (Critic-Infer BLOCKER, reproduced) ---
# Repro before fix: n=1 -> statistic/pvalue/p/ci_low/ci_high ALL nan;
# zero-variance identical arrays -> all nan. A nan propagating into a report
# renders as "None" or silence -- the exact false-green class design.md forbids.

from st_platform.infer.paired import paired_t_test, wilcoxon_signed_rank


def test_paired_t_rejects_single_pair():
    with pytest.raises(ValueError):
        paired_t_test([1.0], [2.0])


def test_paired_t_zero_variance_identical_arrays_returns_exact_no_difference():
    r = paired_t_test([0.3] * 8, [0.3] * 8)
    assert r["p_value"] == 1.0
    assert r["statistic"] == 0.0
    assert r["ci_low"] == r["ci_high"] == 0.0
    assert not any(isinstance(v, float) and v != v for v in r.values())  # no NaN


def test_paired_t_zero_variance_nonzero_mean_raises_rather_than_nan():
    # Every pair differs by exactly +1: t-statistic would divide by zero.
    # NaN must not reach a report; a visible failure must.
    with pytest.raises(ValueError):
        paired_t_test([0.0, 0.0, 0.0], [1.0, 1.0, 1.0])


def test_wilcoxon_all_zero_differences_is_quiet_p1():
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any RuntimeWarning => test fails
        r = wilcoxon_signed_rank([0.5] * 6, [0.5] * 6)
    assert r["p_value"] == 1.0
