"""Immutable evaluation task: content-addressed snapshot + explicit state machine.

Design anchors (AGENTS.md §9 A-4/A-5, §7 D-3):
- The task is a FROZEN snapshot. State changes produce a NEW object, never a mutation.
- ``content_hash`` is a COMPUTED field over the snapshot only => it cannot drift from
  the snapshot, and it is identical in any process for identical inputs (replay).
- ``FAILED -> RUNNING`` is deliberately illegal: a retry is a NEW task (see service).
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, computed_field

from st_platform.common.types import Versioned, sha256_hex, utcnow


class TaskState(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    OBSOLETED = "OBSOLETED"


#: Single source of truth for the lifecycle. FAILED has no outgoing edge to RUNNING:
#: retries mint a new task so a finished task is never overwritten (D-3).
ALLOWED_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.DRAFT: frozenset({TaskState.SUBMITTED, TaskState.OBSOLETED}),
    TaskState.SUBMITTED: frozenset({TaskState.RUNNING, TaskState.FAILED, TaskState.OBSOLETED}),
    TaskState.RUNNING: frozenset({TaskState.DONE, TaskState.FAILED, TaskState.OBSOLETED}),
    TaskState.DONE: frozenset({TaskState.OBSOLETED}),
    TaskState.FAILED: frozenset({TaskState.OBSOLETED}),
    TaskState.OBSOLETED: frozenset(),
}

#: A task may only be retried once it is no longer in flight (DRAFT/RUNNING excluded).
RETRYABLE_PARENT_STATES: frozenset[TaskState] = frozenset(
    {TaskState.SUBMITTED, TaskState.DONE, TaskState.FAILED, TaskState.OBSOLETED}
)


class TaskStateError(Exception):
    """Illegal lifecycle transition or illegal retry of an in-flight task."""


class Task(Versioned):
    task_id: str
    state: TaskState = TaskState.DRAFT
    # --- immutable snapshot (the ONLY inputs to content_hash) ---
    model_version: str
    dataset_id: str
    dataset_version: int
    dataset_sha: str
    seed: int = 0
    params: dict[str, Any] = Field(default_factory=dict)
    # --- lineage ---
    attempt: int = 0
    parent_task_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)

    def snapshot(self) -> dict[str, Any]:
        """Evaluation snapshot. Excludes identity, lineage and timestamps on purpose:
        identical snapshots must hash identically across processes and retries."""
        return {
            "model_version": self.model_version,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_sha": self.dataset_sha,
            "seed": self.seed,
            "params": self.params,
        }

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_hash(self) -> str:
        """sha256 of canonical snapshot JSON. Derived, never stored => never drifts."""
        canonical = json.dumps(self.snapshot(), sort_keys=True, default=str)
        return sha256_hex(canonical)

    def transition_to(self, new_state: TaskState) -> Task:
        """Return a NEW task in ``new_state``; illegal transitions raise."""
        allowed = ALLOWED_TRANSITIONS[self.state]
        if new_state not in allowed:
            allowed_txt = ", ".join(sorted(s.value for s in allowed)) or "<terminal>"
            raise TaskStateError(
                f"illegal transition {self.state.value} -> {new_state.value} "
                f"(allowed: {allowed_txt})"
            )
        return self.model_copy(update={"state": new_state})
