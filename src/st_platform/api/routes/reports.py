"""Reports endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from st_platform.cli.stctl import DEFAULT_STORE_DIR
from st_platform.store import ReportStore

router = APIRouter()
_store = ReportStore(DEFAULT_STORE_DIR)


@router.get("")
def list_reports():
    return {"hashes": _store.list_hashes()}


@router.get("/{report_hash}")
def get_report(report_hash: str):
    try:
        data = _store.get(report_hash)
    except KeyError:
        raise HTTPException(status_code=404, detail="report not found")
    return data