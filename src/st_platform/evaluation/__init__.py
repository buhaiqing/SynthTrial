"""Offline evaluation kernel (P0): task snapshot in, decision-ready report out."""

from st_platform.evaluation.outcome import EvaluationOutcome, GuardrailVerdict
from st_platform.evaluation.pipeline import (
    CORRECTIONS,
    EvaluationError,
    EvaluationPipeline,
    UnalignedCases,
)

__all__ = [
    "CORRECTIONS",
    "EvaluationError",
    "EvaluationOutcome",
    "EvaluationPipeline",
    "GuardrailVerdict",
    "UnalignedCases",
]
