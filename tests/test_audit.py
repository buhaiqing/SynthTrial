import json

from st_platform.audit.ledger import AuditLedger


def test_audit_append_and_verify():
    L = AuditLedger()
    e1 = L.append("task.submitted", {"task_id": "t1"})
    e2 = L.append("task.completed", {"ok": True})
    assert L.verify() is True
    assert len(L) == 2
    assert e2.prev_hash == e1.hash


def test_audit_tamper_detected():
    L = AuditLedger()
    L.append("x", {"a": 1})
    L.append("y", {"b": 2})
    # Clone & tamper in memory
    L2 = L.clone()
    L2._entries[1].payload = {"b": 999}
    # mutating payload should break verification on original L? Original unchanged
    assert L.verify() is True
    # Rebuild hash "matches" but check direct
    assert L2.entries[1].hash == L.entries[1].hash
    # mutate then recompute? Just test chain hash differs by direct check
    recomputed = L2.entries[1].compute_hash(L2.entries[1].prev_hash)
    assert recomputed != L.entries[1].hash


def test_audit_export_chain():
    L = AuditLedger()
    L.append("a", {"x": 1})
    L.append("b", {"y": 2})
    exp = L.export()
    assert exp[0]["prev_hash"] == "genesis"
    assert exp[1]["prev_hash"] == exp[0]["hash"]


# --- T-M7-12: the ledger must be on the real path and survive the process ----
# AuditLedger had one caller (cmd_demo) and was in-memory only, so even that chain
# vanished on exit: a real evaluation left no recoverable evidence behind.


def test_ledger_without_path_stays_in_memory():
    """The no-path ledger is the in-memory one the demo and existing callers use."""
    L = AuditLedger()
    L.append("a", {"x": 1})
    assert L.verify() is True
    assert L.path is None


def test_persisted_ledger_continues_the_chain_across_reopen(tmp_path):
    """A ledger that forgets its chain on restart is not evidence of anything.

    The second process must link to the first one's hash rather than restart at
    genesis, or each run's chain would verify while proving nothing across runs.
    """
    p = tmp_path / "audit.jsonl"
    first = AuditLedger(path=p)
    a = first.append("task.submitted", {"task_id": "t1"})
    assert first.verify() is True

    second = AuditLedger(path=p)
    assert len(second) == 1, "reopening must load what was already written"
    b = second.append("task.completed", {"verdict": "PASS"})

    assert b.prev_hash == a.hash, "chain must continue, not restart"
    assert second.verify() is True
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2, "append-only file, one JSON object per line"


def test_persisted_ledger_exports_what_it_reloaded(tmp_path):
    p = tmp_path / "audit.jsonl"
    AuditLedger(path=p).append("task.submitted", {"task_id": "t7"})
    reloaded = AuditLedger(path=p)
    out = reloaded.export()
    assert len(out) == 1
    assert out[0]["event_type"] == "task.submitted"
    assert out[0]["payload"] == {"task_id": "t7"}
    assert out[0]["created_at"], "a timestamp must survive the round-trip"


def test_tampering_with_the_persisted_file_is_detected(tmp_path):
    """Editing a stored payload must break verification, not silently re-link."""
    p = tmp_path / "audit.jsonl"
    L = AuditLedger(path=p)
    L.append("task.submitted", {"task_id": "t1"})
    L.append("task.completed", {"verdict": "PASS"})

    lines = p.read_text(encoding="utf-8").splitlines()
    forged = json.loads(lines[0])
    forged["payload"]["task_id"] = "attacker"
    lines[0] = json.dumps(forged)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert AuditLedger(path=p).verify() is False, "an edited ledger must not verify"


def test_ledger_appends_rather_than_rewrites(tmp_path):
    """Append-only: the earlier bytes must still be on disk after a second write."""
    p = tmp_path / "audit.jsonl"
    L = AuditLedger(path=p)
    L.append("a", {"n": 1})
    first_bytes = p.read_bytes()
    L.append("b", {"n": 2})
    assert p.read_bytes().startswith(first_bytes), "earlier entries must not be rewritten"
