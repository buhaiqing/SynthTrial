"""Tests for orthogonal / multi-layer experiment architecture (T-M9-06)."""

from __future__ import annotations

import pytest

from st_platform.bucket import Experiment, Layer, assign


def make_layers():
    return [
        Layer("ui", [Experiment("exp_ui_a", "ui", 1), Experiment("exp_ui_b", "ui", 1)]),
        Layer("rank", [Experiment("exp_rank_x", "rank", 2), Experiment("exp_rank_y", "rank", 1)]),
        Layer("empty", []),
    ]


def test_deterministic():
    layers = make_layers()
    r1 = assign("u1", layers, business_line="bl", base_salt="s")
    r2 = assign("u1", layers, business_line="bl", base_salt="s")
    assert r1 == r2


def test_mutual_exclusivity_within_layer():
    layers = [Layer("ui", [Experiment("a", "ui"), Experiment("b", "ui")])]
    # each user gets exactly one of a/b (no None because weights cover all)
    for i in range(200):
        r = assign(f"u{i}", layers)
        assert r["ui"] in ("a", "b")


def test_orthogonality_across_layers():
    layers = [
        Layer("l1", [Experiment("a", "l1"), Experiment("b", "l1")]),
        Layer("l2", [Experiment("x", "l2"), Experiment("y", "l2")]),
    ]
    combos = set()
    for i in range(500):
        r = assign(f"u{i}", layers)
        combos.add((r["l1"], r["l2"]))
    # not perfectly correlated: at least 3 of 4 combos appear
    assert len(combos) >= 3


def test_empty_layer_none():
    layers = [Layer("empty", [])]
    assert assign("u1", layers) == {"empty": None}


def test_validation_errors():
    with pytest.raises(ValueError):
        Experiment("", "l")
    with pytest.raises(ValueError):
        Experiment("e", "")
    with pytest.raises(ValueError):
        Experiment("e", "l", weight=0)
    with pytest.raises(ValueError):
        Layer("", [])
    with pytest.raises(ValueError):
        Layer("l", [Experiment("e", "other")])
    with pytest.raises(ValueError):
        Layer("l", [Experiment("e", "l"), Experiment("e", "l")])


def test_weighted_distribution():
    layers = [Layer("l", [Experiment("heavy", "l", 3), Experiment("light", "l", 1)])]
    counts = {"heavy": 0, "light": 0}
    for i in range(4000):
        counts[assign(f"u{i}", layers)["l"]] += 1
    # heavy should be ~3x light
    ratio = counts["heavy"] / counts["light"]
    assert 2.0 < ratio < 4.5