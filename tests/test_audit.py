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
