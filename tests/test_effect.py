"""Tests for effect sizes."""

import pytest

from st_platform.infer.effect import (
    absolute_lift,
    absolute_lift_ci95,
    relative_lift,
    relative_lift_ci95,
)


def test_absolute_lift():
    assert absolute_lift(10.0, 12.0) == 2.0


def test_relative_lift():
    assert relative_lift(10.0, 12.0) == pytest.approx(0.2)


def test_relative_lift_zero_raises():
    with pytest.raises(ValueError):
        relative_lift(0.0, 5.0)


def test_absolute_ci():
    before = [10.0, 11, 12, 13]
    after = [12.0, 13, 14, 17]
    lo, hi = absolute_lift_ci95(before, after)
    assert lo < hi


def test_relative_ci_zero_mean_raises():
    before = [0.0, 0, 0]
    after = [1.0, 2, 3]
    with pytest.raises(ValueError):
        relative_lift_ci95(before, after)


def test_relative_ci():
    before = [10.0, 11, 12, 13]
    after = [12.0, 13, 14, 17]
    lo, hi = relative_lift_ci95(before, after)
    assert lo < hi
    # equals abs CI / mean before
    alo, ahi = absolute_lift_ci95(before, after)
    bm = 11.5
    assert lo == pytest.approx(alo / bm)
    assert hi == pytest.approx(ahi / bm)
