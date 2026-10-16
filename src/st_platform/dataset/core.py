"""Dataset + contamination detection (st-safety-ish governance)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import Field

from st_platform.common.types import Versioned


class DatasetSplit(str, Enum):
    TRAIN = "train"
    EVAL = "eval"


class AnnotationSummary(Versioned):
    kappa: float
    subjects: int
    note: str = ""


class Dataset(Versioned):
    dataset_id: str
    version: int
    source: str
    split: DatasetSplit
    rows: list[dict] = Field(default_factory=list)
    annotation: AnnotationSummary | None = None
    sha256: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def compute_sha(self) -> str:
        import json

        return hashlib.sha256(
            json.dumps(self.rows, sort_keys=True, default=str).encode()
        ).hexdigest()


class DatasetError(Exception):
    pass


def case_signature(row: dict) -> str:
    """Stable signature for a given eval sample — used in contamination checks."""
    case_id = row.get("case_id", row.get("id", ""))
    text = str(row.get("text", row.get("input", "")))
    return hashlib.sha256(f"{case_id}|{text}".encode()).hexdigest()


def contamination_detect(eval_dataset: Dataset, train_signatures: set[str]) -> dict[str, Any]:
    eval_sigs = {case_signature(r) for r in eval_dataset.rows}
    overlap = eval_sigs & train_signatures
    return {
        "eval_count": len(eval_sigs),
        "train_overlap_count": len(overlap),
        "overlap_ratio": len(overlap) / max(1, len(eval_sigs)),
        "contaminated": bool(overlap),
        "overlap_signatures": sorted(overlap)[:5],
    }
