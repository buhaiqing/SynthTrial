"""Tests for CUPED."""

import numpy as np
import pytest

from st_platform.infer.cuped import (
    assert_pre_treatment_covariate,
    cuped_adjust,
    fit_theta,
)


def test_fit_theta_basic():
    metric = [10.0, 12, 14, 16]
    cov = [1.0, 2, 3, 4]
    theta = fit_theta(metric, cov)
    # metric = 8 + 2*cov -> slope 2
    assert theta == pytest.approx(2.0)


def test_fit_theta_zero_var_raises():
    with pytest.raises(ValueError):
        fit_theta([1.0, 2, 3], [5.0, 5, 5])


def test_adjust_known():
    metric = np.array([10.0, 12, 14, 16])
    cov = np.array([1.0, 2, 3, 4])
    theta = 1.0
    adj = cuped_adjust(metric, cov, theta)
    expected = metric - theta * (cov - cov.mean())
    np.testing.assert_allclose(adj, expected)


def test_adjust_zero_var_raises():
    with pytest.raises(ValueError):
        cuped_adjust([1.0, 2], [5.0, 5], 1.0)


def test_shape_mismatch_raises():
    with pytest.raises(ValueError):
        fit_theta([1.0, 2], [1.0])


# --- Covariate leakage guard ---
# A CUPED covariate must be measured BEFORE treatment. Passing the post-treatment
# metric as its own covariate shrinks the residual to ~0 for any theta, which
# manufactures significance out of nothing. The guard rejects exact identity.


def test_fit_theta_rejects_covariate_that_is_the_metric_by_value():
    metric = [0.4, 0.7, 0.1, 0.9]
    with pytest.raises(ValueError, match="before treatment"):
        fit_theta(metric, list(metric))


def test_fit_theta_rejects_covariate_that_is_the_metric_by_object():
    metric = np.array([0.4, 0.7, 0.1, 0.9])
    with pytest.raises(ValueError, match="before treatment"):
        fit_theta(metric, metric)


def test_fit_theta_allows_a_covariate_that_is_a_scaled_series():
    # The guard rejects identity, not correlation: a legitimate baseline proxy is
    # strongly correlated with the outcome but is a different series.
    metric = [0.4, 0.7, 0.1, 0.9]
    assert fit_theta(metric, [2 * v for v in metric]) == pytest.approx(0.5)


def test_cuped_adjust_rejects_covariate_that_is_the_metric():
    metric = [0.4, 0.7, 0.1, 0.9]
    with pytest.raises(ValueError, match="before treatment"):
        cuped_adjust(metric, list(metric), 1.0)


def test_assert_pre_treatment_covariate_accepts_distinct_series():
    assert_pre_treatment_covariate([1.0, 2.0, 3.0], [10.0, 12.0, 14.0])  # no raise


def test_assert_pre_treatment_covariate_rejects_identical_series():
    with pytest.raises(ValueError, match="before treatment"):
        assert_pre_treatment_covariate([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])


def test_leakage_guard_does_not_mask_shape_mismatch_error():
    with pytest.raises(ValueError, match="same shape"):
        fit_theta([1.0, 2.0], [1.0, 2.0, 3.0])


def test_leakage_guard_treats_matching_nan_columns_as_identical_values():
    # np.array_equal is NaN-blind by default; a NaN metric/covariate pair is
    # still the same series and must not slip past the documented guard.
    nan_metric = np.array([float("nan"), float("nan")])
    with pytest.raises(ValueError, match="before treatment"):
        assert_pre_treatment_covariate(nan_metric, nan_metric.copy())


def test_adjust_shape_mismatch_raises_before_the_leakage_guard():
    with pytest.raises(ValueError, match="same shape"):
        cuped_adjust([1.0, 2.0], [1.0], 1.0)
