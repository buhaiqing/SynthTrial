"""ClickHouse TB-level scan helper (M11 T-M11-02)."""

from __future__ import annotations


def scan_sql(
    table: str,
    *,
    dataset_id: str | None = None,
    parallelism: int = 4,
) -> str:
    """Return a SELECT with partition pruning + parallel settings.

    Partitioning is assumed on (dataset_id, toYYYYMMDD(created_at)).
    """
    where = f"WHERE dataset_id = '{dataset_id}'" if dataset_id else ""
    return (
        f"SELECT * FROM {table} {where} "
        f"SETTINGS max_threads = {parallelism}, max_parallel_replicas = {parallelism}"
    )


def partition_key() -> str:
    return "PARTITION BY (dataset_id, toYYYYMMDD(created_at))"