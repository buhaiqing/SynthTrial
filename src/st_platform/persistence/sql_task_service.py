"""SQL-backed TaskService (M11 T-M11-01): contract identical to in-memory service."""

from __future__ import annotations

import json
from sqlalchemy import MetaData, Table, Column, String, Text, insert, select, update
from sqlalchemy.engine import Engine
from st_platform.task.models import RETRYABLE_PARENT_STATES, Task, TaskState, TaskStateError
from st_platform.task.service import TaskNotFound


metadata = MetaData()
tasks_table = Table(
    "st_tasks",
    metadata,
    Column("task_id", String, primary_key=True),
    Column("content_hash", String, nullable=False, index=True),
    Column("payload", Text, nullable=False),
)


class SqlTaskService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        metadata.create_all(engine)

    def _load(self, task_id: str) -> Task:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(tasks_table.c.payload).where(tasks_table.c.task_id == task_id)
            ).first()
        if row is None:
            raise TaskNotFound(f"unknown task_id {task_id!r}")
        data = json.loads(row[0])
        data.pop("content_hash", None)
        return Task.model_validate(data)

    def submit(self, *, model_version, dataset, seed=0, params=None):
        draft = Task(
            task_id="",
            state=TaskState.SUBMITTED,
            model_version=model_version,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version,
            dataset_sha=dataset.sha256 or dataset.compute_sha(),
            seed=seed,
            params=dict(params or {}),
        )
        with self.engine.connect() as conn:
            existing = conn.execute(
                select(tasks_table.c.task_id).where(tasks_table.c.content_hash == draft.content_hash)
            ).first()
        if existing is not None:
            return self._load(existing[0])
        task = draft.model_copy(update={"task_id": f"t_{draft.content_hash[:12]}"})
        with self.engine.begin() as conn:
            conn.execute(
                insert(tasks_table).values(
                    task_id=task.task_id,
                    content_hash=task.content_hash,
                    payload=json.dumps(task.model_dump(mode="json")),
                )
            )
        return task

    def retry(self, task_id):
        parent = self.get(task_id)
        if parent.state not in RETRYABLE_PARENT_STATES:
            raise TaskStateError(
                f"cannot retry task in state {parent.state.value}; "
                f"retryable: {', '.join(sorted(s.value for s in RETRYABLE_PARENT_STATES))}"
            )
        attempt = parent.attempt + 1
        retry = parent.model_copy(
            update={
                "task_id": f"{parent.task_id}#r{attempt}",
                "state": TaskState.SUBMITTED,
                "attempt": attempt,
                "parent_task_id": parent.task_id,
                "created_at": utcnow(),
            }
        )
        with self.engine.begin() as conn:
            conn.execute(
                insert(tasks_table).values(
                    task_id=retry.task_id,
                    content_hash=retry.content_hash,
                    payload=json.dumps(retry.model_dump(mode="json")),
                )
            )
        return retry

    def transition(self, task_id, new_state):
        moved = self.get(task_id).transition_to(new_state)
        with self.engine.begin() as conn:
            conn.execute(
                update(tasks_table)
                .where(tasks_table.c.task_id == task_id)
                .values(payload=json.dumps(moved.model_dump(mode="json")))
            )
        return moved

    def get(self, task_id):
        return self._load(task_id)

    def list_all(self):
        with self.engine.connect() as conn:
            rows = conn.execute(select(tasks_table.c.payload)).all()
        out = []
        for r in rows:
            data = json.loads(r[0])
            data.pop("content_hash", None)
            out.append(Task.model_validate(data))
        return out