import pytest

from st_platform.lab import Quota, QuotaExceeded, TaskOrchestrator


def test_quota_enforced():
    q = Quota(1)
    orch = TaskOrchestrator(q)
    t = orch.submit(lambda: "task1")
    assert t == "task1"
    assert orch.active == 1
    with pytest.raises(QuotaExceeded):
        orch.submit(lambda: "task2")


def test_complete_frees_slot():
    q = Quota(1)
    orch = TaskOrchestrator(q)
    orch.submit(lambda: "task1")
    orch.complete()
    t2 = orch.submit(lambda: "task2")
    assert t2 == "task2"