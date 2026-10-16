"""Tests for DAG orchestrator (M11 T-M11-03)."""

from __future__ import annotations

from st_platform.orchestration.dag import DagRunner, TaskNode


def test_topo_and_retry():
    r = DagRunner()
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 2:
            raise RuntimeError("boom")
        return "ok"

    r.add(TaskNode("a", lambda: 1))
    r.add(TaskNode("b", flaky, deps=["a"], retries=1))
    res = r.run()
    assert res["a"] == 1
    assert res["b"] == "ok"


def test_cycle_raises():
    r = DagRunner()
    r.add(TaskNode("a", lambda: 1, deps=["b"]))
    r.add(TaskNode("b", lambda: 2, deps=["a"]))
    try:
        r.run()
        assert False
    except ValueError:
        pass