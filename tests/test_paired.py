"""Tests for paired statistics."""

import math

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
    # Default is Yates: max(0, |3-2|-1)^2 / 5 == 0  =>  p = chi2.sf(0, 1) = 1.
    assert res["statistic"] == pytest.approx(0.0)
    assert res["pvalue"] == pytest.approx(1.0)
    # continuity=False reproduces the uncorrected textbook statistic.
    uncorrected = mcnemar(before, after, continuity=False)
    expected_stat = (3 - 2) ** 2 / 5
    assert uncorrected["statistic"] == pytest.approx(expected_stat)
    assert uncorrected["pvalue"] == pytest.approx(float(stats.chi2.sf(expected_stat, 1)))


def test_mcnemar_length_mismatch_raises():
    with pytest.raises(ValueError):
        mcnemar([0, 1], [1])


def test_mcnemar_rejects_non_1d_input():
    with pytest.raises(ValueError, match="1-D"):
        mcnemar([[0, 1], [1, 0]], [1, 1])


def test_mcnemar_case_id_mismatch_raises():
    with pytest.raises(ValueError):
        mcnemar(
            [0, 1, 0], [1, 0, 1], before_case_ids=["a", "b", "c"], after_case_ids=["a", "b", "d"]
        )


# --- Degenerate inputs must fail loud, never NaN (Critic-Infer BLOCKER, reproduced) ---
# Repro before fix: n=1 -> statistic/pvalue/p/ci_low/ci_high ALL nan;
# zero-variance identical arrays -> all nan. A nan propagating into a report
# renders as "None" or silence -- the exact false-green class design.md forbids.


def test_paired_t_rejects_single_pair():
    with pytest.raises(ValueError):
        paired_t_test([1.0], [2.0])


def test_paired_t_zero_variance_identical_arrays_returns_exact_no_difference():
    r = paired_t_test([0.3] * 8, [0.3] * 8)
    assert r["p_value"] == 1.0
    assert r["statistic"] == 0.0
    assert r["ci_low"] == r["ci_high"] == 0.0
    assert not any(isinstance(v, float) and math.isnan(v) for v in r.values())  # no NaN


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


# --- McNemar continuity correction + all-concordant handling ---
# Statistic runs on the discordant cells (n01, n10), 1 degree of freedom:
#   continuity=False : (n01 - n10)^2 / (n01 + n10)
#   continuity=True  : max(0, |n01 - n10| - 1)^2 / (n01 + n10)   (Yates, default)
# Without the floor, |n01 - n10| == 0 would yield 1/(n01+n10) > 0, i.e. a smaller
# p-value than the uncorrected test -- an anti-conservative "correction".


def _mcnemar_fixture(n00: int, n01: int, n10: int, n11: int) -> tuple[list[int], list[int]]:
    """before/after arrays with exactly these 2x2 concordant/discordant counts."""
    before = [1] * n10 + [1] * n11 + [0] * n00 + [0] * n01
    after = [0] * n10 + [1] * n11 + [0] * n00 + [1] * n01
    return before, after


def test_mcnemar_yates_floor_hand_computed_n01_3_n10_2():
    before, after = _mcnemar_fixture(n00=0, n01=3, n10=2, n11=3)
    res = mcnemar(before, after)
    assert res["contingency"] == [[0, 3], [2, 3]]
    assert res["n"] == 8
    # |3 - 2| - 1 == 0  =>  statistic 0, p = chi2.sf(0, 1) = 1
    assert res["statistic"] == pytest.approx(0.0)
    assert res["pvalue"] == pytest.approx(1.0)
    assert res["p_value"] == res["p"] == pytest.approx(1.0)


def test_mcnemar_yates_hand_computed_n01_12_n10_5():
    before, after = _mcnemar_fixture(n00=6, n01=12, n10=5, n11=4)
    res = mcnemar(before, after)
    assert res["contingency"] == [[6, 12], [5, 4]]
    # (|12 - 5| - 1)^2 / 17 == 36/17
    expected = (abs(12 - 5) - 1) ** 2 / 17
    assert expected == pytest.approx(36 / 17)
    assert res["statistic"] == pytest.approx(expected)
    assert res["pvalue"] == pytest.approx(float(stats.chi2.sf(expected, 1)))

    uncorrected = mcnemar(before, after, continuity=False)
    assert uncorrected["statistic"] == pytest.approx((12 - 5) ** 2 / 17)
    assert uncorrected["pvalue"] == pytest.approx(float(stats.chi2.sf((12 - 5) ** 2 / 17, 1)))
    # The correction is conservative: it can never turn a p up into a p down.
    assert res["pvalue"] > uncorrected["pvalue"]


def test_mcnemar_equal_discordant_counts_floor_at_zero():
    before, after = _mcnemar_fixture(n00=4, n01=4, n10=4, n11=4)
    res = mcnemar(before, after)
    # Without the floor the numerator would be 1 => statistic 1/8 and p < 1.
    # Equal discordant counts are zero evidence of a difference.
    assert res["statistic"] == pytest.approx(0.0)
    assert res["pvalue"] == pytest.approx(1.0)


def test_mcnemar_all_concordant_is_explicit_no_evidence():
    before, after = _mcnemar_fixture(n00=5, n01=0, n10=0, n11=3)
    res = mcnemar(before, after)
    assert res["contingency"] == [[5, 0], [0, 3]]
    assert (res["n01"], res["n10"]) == (0, 0)
    assert res["statistic"] == pytest.approx(0.0)
    assert res["pvalue"] == pytest.approx(1.0)
    # Explicit marker: no discordant pair exists, so there is nothing to test.
    # A bare p=1.0 alone would read like "no effect", which is a different claim.
    assert res["degenerate"] == "all_concordant"


def test_mcnemar_contract_keys_present_in_both_branches():
    required = {"statistic", "pvalue", "p_value", "p", "n01", "n10", "contingency", "n"}
    normal = mcnemar(*_mcnemar_fixture(n00=6, n01=12, n10=5, n11=4))
    degenerate = mcnemar(*_mcnemar_fixture(n00=5, n01=0, n10=0, n11=3))
    assert required <= set(normal)
    assert required <= set(degenerate)


def test_mcnemar_continuity_does_not_collide_with_case_id_kwargs():
    before, after = _mcnemar_fixture(n00=6, n01=12, n10=5, n11=4)
    case_ids = [f"c{i}" for i in range(len(before))]
    res = mcnemar(before, after, continuity=False, case_ids=case_ids)
    assert res["statistic"] == pytest.approx((12 - 5) ** 2 / 17)
    with pytest.raises(ValueError):
        mcnemar(before, after, continuity=False, case_ids=case_ids[:-1])
