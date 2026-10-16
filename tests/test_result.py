"""Tests for PairedResult."""

import pytest

from st_platform.infer.result import PairedResult, assert_correction_applied


def _r(pcorr):
    return PairedResult(
        test_name="t",
        n=5,
        statistic=1.0,
        p_raw=0.05,
        p_corrected=pcorr,
        method="paired_t",
        ci_low=0.0,
        ci_high=1.0,
        abs_lift=0.1,
        rel_lift=0.01,
        correction_applied=None if pcorr is None else "holm",
    )


def test_single_no_correction_ok():
    assert_correction_applied([_r(None)])  # does not raise


def test_multi_none_raises():
    with pytest.raises(ValueError):
        assert_correction_applied([_r(0.1), _r(None)])


def test_multi_all_ok():
    assert_correction_applied([_r(0.1), _r(0.2)])


def test_multi_none_raises_when_the_uncorrected_result_comes_first():
    with pytest.raises(ValueError, match="more than one test"):
        assert_correction_applied([_r(None), _r(0.1)])


def test_multi_none_raises_for_dict_results():
    # The report layer consumes dict-shaped results as well.
    with pytest.raises(ValueError, match="more than one test"):
        assert_correction_applied([{"p_corrected": 0.1}, {"p_corrected": None}])


def test_corrected_p_value_of_zero_is_not_missing():
    # Missing is None, not falsy: p_corrected == 0.0 is a real (maximal) result.
    assert_correction_applied([_r(0.0), _r(0.5)])
    assert_correction_applied([{"p_corrected": 0.0}, {"p_corrected": 0.5}])


def test_single_result_object_needs_no_correction():
    assert_correction_applied(_r(None))  # does not raise


def test_empty_results_needs_no_correction():
    assert_correction_applied([])  # does not raise


def test_lone_non_iterable_is_a_single_result_not_a_batch():
    # Precondition is ">1 test was run"; a bare value cannot be a batch.
    assert_correction_applied(42)  # does not raise
