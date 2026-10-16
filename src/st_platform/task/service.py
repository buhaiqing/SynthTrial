"""TaskService: submit / retry / transition / get / list.

In-memory store; contract identical to the P1 SQL repository. Append-only: ``retry``
adds a row, nothing is ever overwritten or deleted (AGENTS §7 D-3).
"""

from __future__ import annotations

from typing import Any

from st_platform.common.types import utcnow
from st_platform.dataset.core import Dataset
from st_platform.task.models import RETRYABLE_PARENT_STATES, Task, TaskState, TaskStateError


class TaskNotFound(LookupError):
    """Unknown task_id."""


class TaskService:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._id_by_hash: dict[str, str] = {}

    def submit(
        self,
        *,
        model_version: str,
        dataset: Dataset,
        seed: int = 0,
        params: dict[str, Any] | None = None,
    ) -> Task:
        """Create (or replay) a task for an immutable evaluation snapshot.

        Idempotent by content: identical snapshots address the same task, because
        identical inputs must reproduce the same result (spec §4). Use ``retry``
        to run an already-addressed task again.
        """
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
        existing_id = self._id_by_hash.get(draft.content_hash)
        if existing_id is not None:
            return self._tasks[existing_id]

        task = draft.model_copy(update={"task_id": f"t_{draft.content_hash[:12]}"})
        self._tasks[task.task_id] = task
        self._id_by_hash[task.content_hash] = task.task_id
        return task

    def retry(self, task_id: str) -> Task:
        """Mint a NEW task from ``task_id``'s snapshot. The parent is never touched."""
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
        self._tasks[retry.task_id] = retry
        return retry

    def transition(self, task_id: str, new_state: TaskState) -> Task:
        """Drive the lifecycle; returns the new immutable task and stores it."""
        moved = self.get(task_id).transition_to(new_state)
        self._tasks[task_id] = moved
        return moved

    def get(self, task_id: str) -> Task:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise TaskNotFound(f"unknown task_id {task_id!r}") from None

    def list_all(self) -> list[Task]:
        return list(self._tasks.values())
