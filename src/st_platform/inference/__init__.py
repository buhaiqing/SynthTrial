"""Inference runner (Slice 2): ModelRunner protocol + deterministic mock."""

from st_platform.inference.runner import (
    REGISTRY,
    RUNNER_REGISTRY,
    RUNNERS,
    MockRunner,
    ModelRunner,
    list_runners,
    run,
    run_batch,
)

__all__ = ["REGISTRY", "RUNNERS", "RUNNER_REGISTRY", "MockRunner", "ModelRunner", "list_runners", "run", "run_batch"]
