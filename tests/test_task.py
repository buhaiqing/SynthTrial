"""Slice 2 — task lifecycle: immutability, content hash, state machine, retry."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from st_platform.dataset.core import Dataset, DatasetSplit
from st_platform.task.models import Task, TaskState, TaskStateError
from st_platform.task.service import TaskNotFound, TaskService

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_dataset(**over) -> Dataset:
    base = {
        "dataset_id": "cards-1.0",
        "version": 3,
        "source": "hospital-A",
        "split": DatasetSplit.EVAL,
        "rows": [{"case_id": "c1", "text": "chest pain"}, {"case_id": "c2", "text": "fever"}],
    }
    base.update(over)
    return Dataset(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------- content hash


def test_submit_yields_submitted_task_with_hex_content_hash():
    task = TaskService().submit(model_version="v2", dataset=make_dataset(), seed=7)
    assert task.state is TaskState.SUBMITTED
    assert len(task.content_hash) == 64  # sha256 hex
    assert task.model_version == "v2"
    assert task.seed == 7


def test_identical_snapshot_replays_same_task_id():
    svc = TaskService()
    a = svc.submit(model_version="v2", dataset=make_dataset(), seed=7, params={"t": 0.7})
    b = svc.submit(model_version="v2", dataset=make_dataset(), seed=7, params={"t": 0.7})
    assert a is b  # identical snapshot REPLAYS the same task, not a new one
    assert a.task_id == b.task_id
    assert a.content_hash == b.content_hash
    assert len(svc.list_all()) == 1


def test_content_hash_changes_when_any_snapshot_field_changes():
    svc = TaskService()
    base = svc.submit(model_version="v2", dataset=make_dataset(), seed=7)
    variants = [
        svc.submit(model_version="v3", dataset=make_dataset(), seed=7),
        svc.submit(model_version="v2", dataset=make_dataset(dataset_id="other"), seed=7),
        svc.submit(model_version="v2", dataset=make_dataset(version=4), seed=7),
        svc.submit(model_version="v2", dataset=make_dataset(sha256="deadbeef"), seed=7),
        svc.submit(model_version="v2", dataset=make_dataset(), seed=8),
        svc.submit(model_version="v2", dataset=make_dataset(), seed=7, params={"t": 0.7}),
    ]
    hashes = {v.content_hash for v in variants}
    assert base.content_hash not in hashes
    assert len(hashes) == len(variants)


def test_params_are_copied_from_caller():
    """Caller mutating its own dict must not change the frozen snapshot."""
    params = {"t": 0.7}
    task = TaskService().submit(model_version="v2", dataset=make_dataset(), params=params)
    before = task.content_hash
    params["t"] = 0.1
    params["new"] = "x"
    assert task.content_hash == before


_HASH_SNIPPET = (
    "from st_platform.dataset.core import Dataset, DatasetSplit\n"
    "from st_platform.task.service import TaskService\n"
    "ds = Dataset(dataset_id='cards-1.0', version=3, source='hospital-A',"
    " split=DatasetSplit.EVAL, rows=[{'case_id': 'c1', 'text': 'chest pain'}],"
    " sha256='sha-xyz')\n"
    "print(TaskService().submit(model_version='v2', dataset=ds, seed=7,"
    " params={'k': [1, 2], 'z': {'b': 1, 'a': 2}}).content_hash)\n"
)


def test_content_hash_stable_across_processes_and_hash_seeds():
    """Same snapshot => same hash in a fresh interpreter under any PYTHONHASHSEED."""
    local = (
        TaskService()
        .submit(
            model_version="v2",
            dataset=make_dataset(rows=[{"case_id": "c1", "text": "chest pain"}], sha256="sha-xyz"),
            seed=7,
            params={"k": [1, 2], "z": {"b": 1, "a": 2}},
        )
        .content_hash
    )
    seen = set()
    for hash_seed in ("0", "1", "424242"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(REPO_ROOT / "src")}
        out = subprocess.run(
            [sys.executable, "-c", _HASH_SNIPPET],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        seen.add(out.stdout.strip())
    assert seen == {local}, f"hash drifted across processes: {seen} != {local}"


def _bare(task_id: str, params: dict[str, Any]) -> Task:
    return Task(task_id=task_id, model_version="v2", dataset_id="d", dataset_version=1,
                dataset_sha="s", seed=7, params=params)


def test_content_hash_independent_of_param_key_order():
    """canonical JSON => key order in the dict cannot change the hash."""
    a = _bare("t_a", {"a": 1, "b": 2, "c": {"y": 1, "x": 2}})
    b = _bare("t_b", {"c": {"x": 2, "y": 1}, "b": 2, "a": 1})
    assert a.content_hash == b.content_hash
    assert a.task_id != b.task_id  # identity is NOT part of the hash


def test_content_hash_respects_list_order():
    """Lists are ordered data, not key sets — sorting them would corrupt the hash."""
    assert _bare("t_a", {"v": [1, 2]}).content_hash != _bare("t_b", {"v": [2, 1]}).content_hash


def test_task_model_is_frozen():
    task = TaskService().submit(model_version="v2", dataset=make_dataset())
    with pytest.raises(ValidationError) as exc:
        task.state = TaskState.DONE  # type: ignore[misc]
    assert exc.value.errors()[0]["type"] == "frozen_instance"


# ---------------------------------------------------------------- state machine


def test_illegal_transition_raises_task_state_error():
    task = Task(task_id="t_x", state=TaskState.DRAFT, model_version="v2",
                dataset_id="d", dataset_version=1, dataset_sha="s")
    with pytest.raises(TaskStateError):
        task.transition_to(TaskState.RUNNING)


def test_legal_happy_path_transitions():
    svc = TaskService()
    task = svc.submit(model_version="v2", dataset=make_dataset())
    assert task.transition_to(TaskState.RUNNING).state is TaskState.RUNNING
    running = svc.transition(task.task_id, TaskState.RUNNING)
    assert running.state is TaskState.RUNNING
    done = svc.transition(task.task_id, TaskState.DONE)
    assert done.state is TaskState.DONE
    assert svc.get(task.task_id).state is TaskState.DONE  # store updated


def test_failed_task_cannot_be_restarted_in_place():
    """AGENTS D-3: retry creates a NEW task; in-place restart is illegal."""
    task = Task(task_id="t_x", state=TaskState.FAILED, model_version="v2",
                dataset_id="d", dataset_version=1, dataset_sha="s")
    with pytest.raises(TaskStateError):
        task.transition_to(TaskState.RUNNING)


def test_obsoleted_is_terminal():
    task = Task(task_id="t_x", state=TaskState.OBSOLETED, model_version="v2",
                dataset_id="d", dataset_version=1, dataset_sha="s")
    with pytest.raises(TaskStateError):
        task.transition_to(TaskState.SUBMITTED)


# ---------------------------------------------------------------- retry semantics


def test_retry_creates_new_task_and_never_mutates_parent():
    svc = TaskService()
    parent = svc.submit(model_version="v2", dataset=make_dataset(), seed=7)
    failed = svc.transition(parent.task_id, TaskState.FAILED)

    retry = svc.retry(parent.task_id)

    assert retry.task_id != parent.task_id
    assert retry.parent_task_id == parent.task_id
    assert retry.attempt == failed.attempt + 1
    assert retry.state is TaskState.SUBMITTED
    assert retry.content_hash == parent.content_hash  # same inputs => same result
    # parent untouched, both rows retained (append-only)
    assert svc.get(parent.task_id).state is TaskState.FAILED
    assert len(svc.list_all()) == 2


def test_retry_lineage_increments_attempt_and_stays_unique():
    svc = TaskService()
    t0 = svc.submit(model_version="v2", dataset=make_dataset())
    t0 = svc.transition(t0.task_id, TaskState.FAILED)
    t1 = svc.retry(t0.task_id)
    t1 = svc.transition(t1.task_id, TaskState.FAILED)
    t2 = svc.retry(t1.task_id)
    assert (t0.attempt, t1.attempt, t2.attempt) == (0, 1, 2)
    assert len({t0.task_id, t1.task_id, t2.task_id}) == 3
    assert t2.parent_task_id == t1.task_id
    assert len(svc.list_all()) == 3


def test_retry_of_running_task_is_rejected():
    svc = TaskService()
    task = svc.submit(model_version="v2", dataset=make_dataset())
    svc.transition(task.task_id, TaskState.RUNNING)
    with pytest.raises(TaskStateError):
        svc.retry(task.task_id)


# ---------------------------------------------------------------- lookup


def test_get_unknown_task_raises_task_not_found():
    with pytest.raises(TaskNotFound):
        TaskService().get("t_nope")


def test_list_all_returns_insertion_order_snapshot():
    svc = TaskService()
    a = svc.submit(model_version="v1", dataset=make_dataset())
    b = svc.submit(model_version="v2", dataset=make_dataset())
    assert [t.task_id for t in svc.list_all()] == [a.task_id, b.task_id]
    svc.list_all().clear()  # returned list is a copy
    assert len(svc.list_all()) == 2
