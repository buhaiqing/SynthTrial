"""Tests for ClickHouse scan helper (M11 T-M11-02)."""

from __future__ import annotations

from st_platform.persistence.clickhouse_scan import partition_key, scan_sql


def test_scan_sql_contains_partition_and_parallelism():
    sql = scan_sql("events", dataset_id="d1", parallelism=8)
    assert "WHERE dataset_id = 'd1'" in sql
    assert "max_threads = 8" in sql


def test_partition_key():
    assert "PARTITION BY" in partition_key()