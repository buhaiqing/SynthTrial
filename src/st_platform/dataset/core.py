"""Dataset + contamination detection (st-safety-ish governance)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
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


def contamination_detect(
    eval_dataset: Dataset, train_signatures: Iterable[str] | None
) -> dict[str, Any]:
    """Compare the eval set against a training corpus.

    ``train_signatures=None`` means **no corpus was supplied**, so nothing can be
    concluded; the result then carries ``train_corpus_supplied=False`` and a
    ``None`` conclusion with ``None`` counts. Reporting ``0``/``False`` there would
    certify a check that never ran (CP-7: record 「没采到」 as null, not 0; design §3.2
    「不可见 ≠ 未曝光」). Any iterable — including an empty one — counts as supplied:
    "the corpus is empty" is a measurement, "there is no corpus" is not.
    """
    eval_sigs = {case_signature(r) for r in eval_dataset.rows}
    if train_signatures is None:
        return {
            "train_corpus_supplied": False,
            "eval_count": len(eval_sigs),
            "train_overlap_count": None,
            "overlap_ratio": None,
            "contaminated": None,
            "overlap_signatures": None,
        }
    overlap = eval_sigs & set(train_signatures)
    return {
        "train_corpus_supplied": True,
        "eval_count": len(eval_sigs),
        "train_overlap_count": len(overlap),
        "overlap_ratio": len(overlap) / max(1, len(eval_sigs)),
        "contaminated": bool(overlap),
        "overlap_signatures": sorted(overlap)[:5],
    }


def contamination_violated(contamination: Mapping[str, Any] | None) -> bool:
    """Read the contamination redline's verdict out of a detection result.

    **Fail closed**: anything other than a measured ``False`` — unknown (``None``),
    a missing key, or no result at all — counts as a violation. This mirrors the two
    precedents already in the codebase, where "did not check" is never reported as
    "did not happen": an unevaluated redline raises instead of passing
    (``EvaluationPipeline.safety_verdict``), and an unregistered rule id is BLOCK
    rather than PASS (``SafetyChecker.check``). Only ``contamination_detect`` decides
    what the shape means; redlines ask this function so there is one reader.
    """
    if not isinstance(contamination, Mapping):
        return True
    return contamination.get("contaminated") is not False
