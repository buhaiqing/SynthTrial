"""Tests for CUPED."""

import numpy as np
import pytest

from st_platform.infer.cuped import cuped_adjust, fit_theta


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
