"""Trigger verification for P2 causal inference (M10 T-M10-01)."""

from __future__ import annotations


def check_triggers(*, reports_count: int, bucket_deviations_ge_10pp: int, compliance_approval: bool) -> dict:
    checks = {
        "reports_ge_50": reports_count >= 50,
        "buckets_ge_3": bucket_deviations_ge_10pp >= 3,
        "compliance_approval": bool(compliance_approval),
    }
    return {"checks": checks, "all_met": all(checks.values())}