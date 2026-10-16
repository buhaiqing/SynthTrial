"""Slice 2 — inference runner: determinism, protocol pluggability, batch run."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from st_platform.dataset.core import Dataset, DatasetSplit
from st_platform.inference.runner import (
    RUNNER_REGISTRY,
    MockRunner,
    ModelRunner,
    list_runners,
    run_batch,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_dataset(rows: list[dict]) -> Dataset:
    return Dataset(dataset_id="cards-1.0", version=1, source="hospital-A",
                   split=DatasetSplit.EVAL, rows=rows)


# ---------------------------------------------------------------- determinism


def test_predict_is_deterministic_across_calls():
    runner = MockRunner()
    row = {"case_id": "c1", "text": "chest pain"}
    assert runner.predict(row) == runner.predict(row) == runner.predict(dict(row))


def test_predict_differs_per_case_id():
    runner = MockRunner()
    a = runner.predict({"case_id": "c1", "text": "x"})
    b = runner.predict({"case_id": "c2", "text": "x"})
    assert a["case_id"] == "c1" and b["case_id"] == "c2"
    assert a["score"] != b["score"]


def test_predict_shape_and_range():
    out = MockRunner().predict({"case_id": "c1", "text": "x"})
    assert set(out) >= {"case_id", "score", "label", "runner", "model_version"}
    assert 0.0 <= out["score"] <= 1.0
    assert out["label"] in (0, 1)
    assert out["runner"] == "mock"


def test_fresh_instances_agree_on_same_case():
    """Determinism must not depend on instance state (Slice 3 replays runners)."""
    row = {"case_id": "c9", "text": "z"}
    assert MockRunner().predict(row) == MockRunner().predict(row)


def test_model_version_changes_predictions_but_stays_deterministic():
    """Paired stats need per-version scores; each version is still a pure function."""
    row = {"case_id": "c1", "text": "x"}
    v1, v2 = MockRunner(model_version="v1"), MockRunner(model_version="v2")
    assert v1.predict(row)["score"] != v2.predict(row)["score"]
    assert v2.predict(row) == v2.predict(row)
    assert v2.predict(row)["model_version"] == "v2"


_PREDICT_SNIPPET = (
    "from st_platform.inference.runner import MockRunner\n"
    "print(MockRunner().predict({'case_id': 'c1', 'text': 'chest pain'}))\n"
)


def test_predict_stable_across_processes_and_hash_seeds():
    local = str(MockRunner().predict({"case_id": "c1", "text": "chest pain"}))
    seen = set()
    for hash_seed in ("0", "1", "424242"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(REPO_ROOT / "src")}
        out = subprocess.run(
            [sys.executable, "-c", _PREDICT_SNIPPET],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        seen.add(out.stdout.strip())
    assert seen == {local}, f"prediction drifted across processes: {seen}"


def test_predict_without_case_id_still_deterministic():
    row = {"text": "no id here"}
    assert MockRunner().predict(row) == MockRunner().predict(row)
    assert MockRunner().predict(row)["case_id"] == ""


# ---------------------------------------------------------------- protocol seam


def test_mock_runner_satisfies_protocol():
    assert isinstance(MockRunner(), ModelRunner)


def test_registry_lists_mock_runner():
    assert "mock" in list_runners()
    assert RUNNER_REGISTRY["mock"] is MockRunner


class ConstantRunner:
    """Third-party runner: proves the seam is structural, not MockRunner-specific."""

    name = "constant"

    def predict(self, row: dict) -> dict:
        return {"case_id": row.get("case_id", ""), "score": 1.0, "label": 1, "runner": "constant"}


def test_batch_runs_any_runner_implementing_the_protocol():
    ds = make_dataset([{"case_id": "c1", "text": "a"}, {"case_id": "c2", "text": "b"}])
    preds = run_batch(ConstantRunner(), ds)
    assert [p["case_id"] for p in preds] == ["c1", "c2"]
    assert all(p["score"] == 1.0 for p in preds)


# ---------------------------------------------------------------- batch


def test_run_batch_covers_every_dataset_row_once():
    ds = make_dataset([{"case_id": f"c{i}", "text": f"t{i}"} for i in range(5)])
    preds = run_batch(MockRunner(), ds)
    assert [p["case_id"] for p in preds] == [f"c{i}" for i in range(5)]
    assert len(preds) == len(ds.rows)


def test_run_batch_is_reproducible_end_to_end():
    ds = make_dataset([{"case_id": "c1", "text": "a"}, {"case_id": "c2", "text": "b"}])
    assert run_batch(MockRunner(), ds) == run_batch(MockRunner(), ds)


def test_run_batch_on_empty_dataset():
    assert run_batch(MockRunner(), make_dataset([])) == []
