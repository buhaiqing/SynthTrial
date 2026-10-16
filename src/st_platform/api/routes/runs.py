"""Runs endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from st_platform.dataset.core import Dataset, DatasetSplit
from st_platform.task.service import TaskService

router = APIRouter()

_service = TaskService()


class RunRequest(BaseModel):
    model_version: str = "candidate"
    dataset: str
    seed: int = 0


@router.post("")
def submit_run(req: RunRequest):
    ds_path = Path(req.dataset)
    if not ds_path.exists():
        raise HTTPException(status_code=404, detail="dataset not found")
    import json as _json
    raw = _json.loads(ds_path.read_text(encoding="utf-8"))
    from st_platform.dataset.core import Dataset, DatasetSplit

    dataset = Dataset(
        dataset_id=raw.get("dataset_id", "dataset"),
        version=int(raw.get("version", 1)),
        source=f"file:{ds_path}",
        split=DatasetSplit.EVAL,
        rows=raw.get("rows", []),
    )
    task = _service.submit(model_version=req.model_version, dataset=dataset, seed=req.seed, params={})
    return {"task_id": task.task_id, "state": task.state.value}


@router.get("/{task_id}")
def get_run(task_id: str):
    t = _service.get(task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="task not found")
    return {"task_id": t.task_id, "state": t.state.value}