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
