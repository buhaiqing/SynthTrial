from st_platform.bucket import bucket, murmur3_32


def test_deterministic_same_inputs():
    a = bucket("u1", "exp1", business_line="search", salt="s", n_buckets=2)
    b = bucket("u1", "exp1", business_line="search", salt="s", n_buckets=2)
    assert a == b


def test_different_users_not_all_same():
    groups = {bucket(f"u{i}", "exp1", n_buckets=2) for i in range(100)}
    assert groups == {0, 1}


def test_n_buckets_range():
    for n in (2, 3, 10, 100):
        g = bucket("u1", "exp1", n_buckets=n)
        assert 0 <= g < n


def test_invalid_n_buckets():
    import pytest

    with pytest.raises(ValueError):
        bucket("u1", "exp1", n_buckets=1)
    with pytest.raises(ValueError):
        bucket("u1", "exp1", n_buckets=101)


def test_murmur_stable():
    assert murmur3_32("abc") == murmur3_32("abc")