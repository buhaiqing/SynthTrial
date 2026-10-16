"""Tests for SQL-backed TaskService (M11 T-M11-01)."""

from __future__ import annotations

from sqlalchemy import create_engine

from st_platform.dataset.core import Dataset, DatasetSplit
from st_platform.persistence.sql_task_service import SqlTaskService
from st_platform.task.models import TaskState


def make_dataset():
    return Dataset(
        dataset_id="d", version=1, source="x", split=DatasetSplit.EVAL, rows=[{"case_id": "c1"}]
    )


def test_submit_get_transition_persist():
    engine = create_engine("sqlite:///:memory:")
    svc = SqlTaskService(engine)
    ds = make_dataset()
    t = svc.submit(model_version="c", dataset=ds, seed=1, params={})
    svc.transition(t.task_id, TaskState.RUNNING)
    svc2 = SqlTaskService(engine)
    got = svc2.get(t.task_id)
    assert got.state.value == "RUNNING"
    assert svc2.list_all()


def test_idempotent_submit():
    engine = create_engine("sqlite:///:memory:")
    svc = SqlTaskService(engine)
    ds = make_dataset()
    a = svc.submit(model_version="c", dataset=ds, seed=1, params={})
    b = svc.submit(model_version="c", dataset=ds, seed=1, params={})
    assert a.task_id == b.task_id