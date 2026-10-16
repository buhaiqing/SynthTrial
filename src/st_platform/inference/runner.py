"""Model runners: a structural seam (``ModelRunner``) plus a deterministic mock.

Determinism contract: ``predict`` is a PURE function of ``(model_version, row)``.
The RNG is seeded per call from sha256 of the case id, so results are identical
across calls, instances and processes — no shared/global RNG state (Slice 3 replays
batch vectors and compares them, so drift would silently fake a statistical effect).
"""

from __future__ import annotations

import json
import random
from typing import Any, Protocol, runtime_checkable

from st_platform.common.types import sha256_hex


@runtime_checkable
class ModelRunner(Protocol):
    def predict(self, row: dict) -> dict:
        """Score one dataset row. Must return a JSON-serializable dict."""
        ...


class MockRunner:
    """Deterministic stand-in for a real model.

    Score = Mersenne-Twister draw seeded by sha256(f"{model_version}|{case_id}").
    With the default ``model_version=""`` this reduces to a pure function of the
    case id. ``model_version`` is a seed component (not extra state) so paired
    comparison across candidate versions yields real per-case differences.
    """

    name = "mock"

    def __init__(self, *, model_version: str = "", label_threshold: float = 0.5) -> None:
        self.model_version = model_version
        self.label_threshold = label_threshold

    def predict(self, row: dict) -> dict:
        case_id = str(row.get("case_id", row.get("id", "")))
        seed_src = (
            f"{self.model_version}|{case_id}"
            if case_id
            else json.dumps(row, sort_keys=True, default=str)
        )
        score = round(random.Random(int(sha256_hex(seed_src)[:16], 16)).random(), 6)
        return {
            "case_id": case_id,
            "score": score,
            "label": int(score >= self.label_threshold),
            "runner": self.name,
            "model_version": self.model_version,
        }

    def run(self, dataset) -> list[dict]:
        return run_batch(self, dataset)

    def run_batch(self, dataset) -> list[dict]:  # type: ignore[override]
        return run_batch(self, dataset)


RUNNER_REGISTRY: dict[str, type[ModelRunner]] = {"mock": MockRunner}


def list_runners() -> list[str]:
    """Names of registered runner classes (sorted)."""
    return sorted(RUNNER_REGISTRY)


def run_batch(runner: ModelRunner, dataset) -> list[dict[str, Any]]:
    """Run ``runner`` over every row of ``dataset``; order matches ``dataset.rows``.

    Accepts either a Dataset (with ``.rows``) or a plain iterable of rows.
    """
    rows = getattr(dataset, "rows", dataset)
    return [runner.predict(row) for row in (rows or [])]


def run(runner: ModelRunner, dataset) -> list[dict[str, Any]]:
    """Alias for :func:`run_batch` (ergonomics)."""
    return run_batch(runner, dataset)


# Convenience back-compat names.
RUNNERS = RUNNER_REGISTRY
REGISTRY = RUNNER_REGISTRY
