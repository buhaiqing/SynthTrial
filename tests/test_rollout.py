from st_platform.bucket.rollout import RolloutController


def test_rollout_reflects_percent_immediately():
    c = RolloutController()
    c.set_percent("exp1", 50)
    assert c.get_percent("exp1") == 50


def test_rollout_validation():
    import pytest

    c = RolloutController()
    with pytest.raises(ValueError):
        c.set_percent("exp1", -1)
    with pytest.raises(ValueError):
        c.set_percent("exp1", 101)


def test_rollout_enabled_bounds():
    c = RolloutController()
    c.set_percent("exp1", 0)
    assert c.is_enabled("u1", "exp1") is False
    c.set_percent("exp1", 100)
    assert c.is_enabled("u1", "exp1") is True