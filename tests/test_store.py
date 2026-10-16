"""Content-addressed report store (AGENTS.md §9 A-5)."""

from __future__ import annotations

import pytest

from st_platform.store import ReportStore, StoreConflict


def test_save_returns_content_hash_and_is_retrievable(tmp_path):
    store = ReportStore(tmp_path)
    payload = {"task_id": "t1", "model_version": "m2", "verdict": "PASS"}
    h = store.save(payload)
    assert len(h) == 64
    assert store.get(h) == payload
    assert h in store.list_hashes()


def test_same_payload_is_stored_once(tmp_path):
    store = ReportStore(tmp_path)
    payload = {"a": 1}
    h1 = store.save(payload)
    h2 = store.save(dict(payload))
    assert h1 == h2
    assert store.list_hashes() == [h1]


def test_key_order_does_not_change_hash(tmp_path):
    store = ReportStore(tmp_path)
    assert store.save({"a": 1, "b": 2}) == store.save({"b": 2, "a": 1})


def test_different_payloads_get_different_hashes(tmp_path):
    store = ReportStore(tmp_path)
    assert store.save({"a": 1}) != store.save({"a": 2})


def test_store_is_append_only_no_collision_overwrite(tmp_path):
    """A hash collision / re-save with differing bytes must be refused, not
    silently overwritten -- the audit chain depends on immutability."""
    store = ReportStore(tmp_path)
    h = store.save({"a": 1})
    target = store._path_for(h)
    target.write_text('{"a": 999}')  # simulate tampering / collision
    with pytest.raises(StoreConflict):
        store.save({"a": 1})
    assert target.read_text() == '{"a": 999}'  # refusal did not clobber


def test_get_unknown_raises(tmp_path):
    store = ReportStore(tmp_path)
    with pytest.raises(KeyError):
        store.get("0" * 64)


def test_store_creates_root_lazily(tmp_path):
    root = tmp_path / "nested" / "reports"
    assert not root.exists()
    store = ReportStore(root)
    store.save({"x": 1})
    assert root.exists()


def test_summary_view_for_listing(tmp_path):
    store = ReportStore(tmp_path)
    store.save(
        {"task_id": "t1", "model_version": "m2", "verdict": "BLOCK", "created_at": "2026-01-01"}
    )
    s = store.summaries()[0]
    assert s["task_id"] == "t1"
    assert s["verdict"] == "BLOCK"
