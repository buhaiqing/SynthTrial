"""In-memory quota-based task orchestrator."""

from __future__ import annotations


class QuotaExceeded(Exception):
    pass


class Quota:
    def __init__(self, max_tasks: int) -> None:
        if max_tasks < 1:
            raise ValueError("max_tasks must be >= 1")
        self.max_tasks = max_tasks


class TaskOrchestrator:
    def __init__(self, quota: Quota) -> None:
        self.quota = quota
        self._active = 0

    @property
    def active(self) -> int:
        return self._active

    def submit(self, task_factory):
        if self._active >= self.quota.max_tasks:
            raise QuotaExceeded("quota exceeded")
        task = task_factory()
        self._active += 1
        return task

    def complete(self) -> None:
        if self._active > 0:
            self._active -= 1
