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
    # Deliberately NOT `abs CI / before_mean`: that treats the sampled baseline
    # mean as a known constant and understates uncertainty (docs/design.md 4.1).
    # The interval is the delta-method one, pinned below against scipy.
    import numpy as np

    before_a = np.asarray(before, dtype=float)
    after_a = np.asarray(after, dtype=float)
    n = before_a.size
    b_bar = before_a.mean()
    a_bar = after_a.mean()
    var_a = after_a.var(ddof=1) / n
    var_b = before_a.var(ddof=1) / n
    cov_ab = np.cov(after_a, before_a, ddof=1)[0, 1] / n
    se = np.sqrt(var_a / b_bar**2 + (a_bar**2 / b_bar**4) * var_b - 2 * (a_bar / b_bar**3) * cov_ab)
    from scipy import stats as _st

    t = _st.t.ppf(0.975, n - 1)
    point = (a_bar - b_bar) / b_bar
    assert lo == pytest.approx(point - t * se)
    assert hi == pytest.approx(point + t * se)


# --- relative lift CI: denominator variance must be accounted for ---
# Regression guard: the naive implementation divided the absolute CI by
# before_mean, treating a SAMPLE mean as a known constant. That understates
# uncertainty, and the error explodes as before_mean -> 0 (rare adverse events).


def test_naive_ci_would_declare_significance_the_honest_ci_cannot():
    """The false-green this guards against, stated clinically.

    On a deterministic low-prevalence fixture the naive definition (absolute CI
    divided by the baseline mean) yields an interval entirely above zero --
    "statistically significant improvement". The delta-method interval, which
    accounts for the baseline mean's own sampling variance, spans zero and
    cannot rule out no effect. A tool reporting the narrower one would let an
    unproven change through.
    """
    import numpy as np

    from st_platform.infer.effect import absolute_lift_ci95, relative_lift_ci95

    before = np.array([1.0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0])
    after = np.array([1.0, 1, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 1])

    alo, ahi = absolute_lift_ci95(before, after)
    naive_lo, naive_hi = alo / before.mean(), ahi / before.mean()
    lo, hi = relative_lift_ci95(before, after)

    assert naive_lo > 0, "fixture assumption: naive CI excludes zero"
    assert lo < 0 < hi, (
        f"honest CI [{lo:.4f}, {hi:.4f}] should span zero; "
        f"naive was [{naive_lo:.4f}, {naive_hi:.4f}]"
    )


def test_relative_lift_ci_symmetric_about_point_estimate():
    import numpy as np

    from st_platform.infer.effect import relative_lift, relative_lift_ci95

    rng = np.random.default_rng(11)
    before = rng.normal(0.5, 0.1, 200)
    after = before + rng.normal(0.02, 0.01, 200)
    lo, hi = relative_lift_ci95(before, after)
    point = relative_lift(before.mean(), after.mean())
    assert abs((point - lo) - (hi - point)) < 1e-9


def test_relative_lift_ci_matches_delta_method_reference():
    import numpy as np

    from st_platform.infer.effect import relative_lift_ci95

    before = np.array([0.4, 0.5, 0.6, 0.5, 0.55, 0.45, 0.5, 0.62, 0.48, 0.52])
    after = np.array([0.5, 0.55, 0.65, 0.58, 0.6, 0.5, 0.55, 0.7, 0.52, 0.6])

    n = before.size
    b_bar, a_bar = before.mean(), after.mean()
    var_a = after.var(ddof=1) / n
    var_b = before.var(ddof=1) / n
    cov_ab = np.cov(after, before, ddof=1)[0, 1] / n
    se = np.sqrt(var_a / b_bar**2 + (a_bar**2 / b_bar**4) * var_b - 2 * (a_bar / b_bar**3) * cov_ab)
    from scipy import stats

    t = stats.t.ppf(0.975, n - 1)
    point = (a_bar - b_bar) / b_bar
    exp_lo, exp_hi = point - t * se, point + t * se

    lo, hi = relative_lift_ci95(before, after)
    assert abs(lo - exp_lo) < 1e-9
    assert abs(hi - exp_hi) < 1e-9


def test_relative_lift_ci_rejects_single_pair_instead_of_point_interval():
    """n=1 must raise: a zero-width interval around one observation is false
    certainty (reproduced: returned (0.4, 0.4))."""
    with pytest.raises(ValueError):
        relative_lift_ci95([0.5], [0.7])


def test_absolute_lift_ci_rejects_single_pair():
    with pytest.raises(ValueError):
        absolute_lift_ci95([0.5], [0.7])
