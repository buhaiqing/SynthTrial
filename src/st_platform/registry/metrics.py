"""Metric registry (st-ledger P0 subset): metric definitions with versioning + history."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import Field

from st_platform.common.types import Versioned


class MetricKind(str, Enum):
    RATE = "rate"
    COUNT = "count"
    LATENCY = "latency"
    SCORE = "score"
    TEXT = "text"


class Direction(str, Enum):
    HIGHER_BETTER = "higher_better"
    LOWER_BETTER = "lower_better"


class MetricDefinition(Versioned):
    metric_id: str
    version: int = 1
    name: str
    kind: MetricKind
    direction: Direction = Direction.HIGHER_BETTER
    description: str = ""
    formula: str = ""
    lower_limit: float | None = None  # for reference only
    upper_limit: float | None = None
    tags: list[str] = Field(default_factory=list)
    owner: str = "unknown"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RegistryError(Exception):
    pass


class MetricRegistry:
    """In-memory registry with append-only version history.

    Production: Database. Contract identical."""

    _store: dict[str, list[MetricDefinition]]

    def __init__(self) -> None:
        self._store = {}

    def register(self, metric: MetricDefinition) -> MetricDefinition:
        existing = self._store.get(metric.metric_id)
        if existing and metric.version != len(existing) + 1:
            raise RegistryError("version must increment by 1")
        entry = metric.model_copy(update={"version": (len(existing) + 1) if existing else 1})
        self._store.setdefault(metric.metric_id, []).append(entry)
        return entry

    def latest(self, metric_id: str) -> MetricDefinition | None:
        hist = self._store.get(metric_id)
        return hist[-1] if hist else None

    def all_versions(self, metric_id: str) -> list[MetricDefinition]:
        return list(self._store.get(metric_id, []))

    def list_ids(self) -> list[str]:
        return sorted(self._store.keys())

    def validate_metric_exists(self, metric_id: str) -> None:
        if metric_id not in self._store:
            raise RegistryError(f"unknown metric id {metric_id!r}")


def make_uid(prefix: str = "m") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"
