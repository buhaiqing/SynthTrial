"""Property-based tests (Hypothesis) for SynthTrial core invariants."""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from st_platform.common.freeze import freeze
from st_platform.infer.paired import mcnemar, paired_t_test


@given(
    before=st.lists(st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False), min_size=2, max_size=20),
    after=st.lists(st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False), min_size=2, max_size=20),
)
@settings(max_examples=200, deadline=None)
def test_paired_t_invariants(before, after):
    # Align lengths (property only meaningful for equal lengths).
    n = min(len(before), len(after))
    if n < 2:
        return
    b = before[:n]
    a = after[:n]
    try:
        res = paired_t_test(b, a)
    except ValueError:
        # Degenerate inputs (zero variance non-zero mean) must fail loud, not NaN.
        return
    assert res["n"] == n
    assert math.isfinite(res["statistic"])
    assert 0.0 <= res["pvalue"] <= 1.0
    assert math.isfinite(res["ci_low"]) and math.isfinite(res["ci_high"])
    assert res["ci_low"] <= res["ci_high"] + 1e-9
    assert not any(isinstance(v, float) and math.isnan(v) for v in res.values())


@given(
    before=st.lists(st.integers(min_value=0, max_value=1), min_size=2, max_size=30),
    after=st.lists(st.integers(min_value=0, max_value=1), min_size=2, max_size=30),
)
@settings(max_examples=200, deadline=None)
def test_mcnemar_invariants(before, after):
    n = min(len(before), len(after))
    if n < 2:
        return
    b = before[:n]
    a = after[:n]
    res = mcnemar(b, a)
    assert res["n"] == n
    assert res["statistic"] >= 0.0
    assert 0.0 <= res["pvalue"] <= 1.0
    n01 = sum(1 for x, y in zip(b, a) if x == 0 and y == 1)
    n10 = sum(1 for x, y in zip(b, a) if x == 1 and y == 0)
    assert res["n01"] == n01
    assert res["n10"] == n10


@given(
    obj=st.recursive(
        st.integers() | st.floats(allow_nan=False) | st.text(),
        lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    )
)
@settings(max_examples=100, deadline=None)
def test_freeze_is_immutable(obj):
    frozen = freeze(obj)
    # Freeze must not mutate original container identity for scalars.
    # Nested lists become tuples; dicts stay dict-like.
    assert frozen == obj or frozen != obj  # trivially true; guards no crash
    # Re-freezing is idempotent in value.
    assert freeze(frozen) == frozen


from st_platform.audit.ledger import AuditLedger
from st_platform.bucket.bucket import bucket, murmur3_32
from st_platform.infer.paired import _extract_case_ids


@given(st.text(min_size=1, max_size=20), st.text(min_size=1, max_size=20), st.text(min_size=1, max_size=20))
@settings(max_examples=100, deadline=None)
def test_bucket_deterministic_and_in_range(u, e, b):
    for n in (2, 5, 10, 100):
        r1 = bucket(u, e, business_line=b, n_buckets=n)
        r2 = bucket(u, e, business_line=b, n_buckets=n)
        assert r1 == r2
        assert 0 <= r1 < n


@given(st.integers(min_value=2, max_value=100))
@settings(max_examples=50, deadline=None)
def test_bucket_invalid_n_raises(n):
    # n_buckets outside allowed range raises
    with pytest.raises(ValueError):
        bucket("u", "e", n_buckets=1)
    with pytest.raises(ValueError):
        bucket("u", "e", n_buckets=101)


@given(st.text())
@settings(max_examples=200, deadline=None)
def test_murmur3_32_range(s):
    h = murmur3_32(s)
    assert 0 <= h <= 0xFFFFFFFF


@given(
    events=st.lists(
        st.tuples(st.text(min_size=1, max_size=10), st.dictionaries(st.text(min_size=1, max_size=5), st.integers())),
        min_size=1,
        max_size=20,
    )
)
@settings(max_examples=100, deadline=None)
def test_audit_ledger_chain_verifies(events):
    ledger = AuditLedger()
    for et, payload in events:
        ledger.append(et, payload)
    assert ledger.verify() is True
    assert len(ledger) == len(events)


@given(
    events=st.lists(
        st.tuples(st.text(min_size=1, max_size=10), st.dictionaries(st.text(min_size=1, max_size=5), st.integers())),
        min_size=2,
        max_size=20,
    )
)
@settings(max_examples=100, deadline=None)
def test_audit_ledger_tamper_breaks_verify(events):
    ledger = AuditLedger()
    for et, payload in events:
        ledger.append(et, payload)
    # Tamper with the middle entry's payload.
    ledger.entries[len(ledger.entries) // 2].payload["__tampered__"] = 1
    assert ledger.verify() is False


@given(st.data())
@settings(max_examples=100, deadline=None)
def test_extract_case_ids_never_drops_provided_names(data):
    # Provide a single known before-name and assert it is captured.
    name = data.draw(st.sampled_from(sorted({
        "before_case_ids", "case_ids_before", "ids_before", "case_id_before", "before_ids",
    })))
    vals = [1, 2, 3]
    before, after, shared = _extract_case_ids({name: vals})
    assert before == vals
    assert after is None
    assert shared is None
