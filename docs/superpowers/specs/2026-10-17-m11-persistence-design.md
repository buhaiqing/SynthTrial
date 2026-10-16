# SynthTrial M11 · Persistence (Postgres + ClickHouse) Design Spec

> Status: Done
> Date: 2026-10-17
> Scope: T-M11-01 Postgres TaskService adapter + T-M11-02 ClickHouse scan helper.

## 1. Problem

P0 TaskService 是内存的，进程重启丢失任务。生产需要持久化；TB 级扫描需要 ClickHouse 分区/并行度。

## 2. Solution

- `src/st_platform/persistence/sql_task_service.py`: `SqlTaskService` implementing same contract as `TaskService` (submit/get/transition/list) backed by SQLAlchemy (Postgres in prod, SQLite for tests).
- `src/st_platform/persistence/clickhouse_scan.py`: `scan_partitions(...)` helper describing partition strategy + parallelism; returns SQL template.

## 3. Contracts

- `SqlTaskService(engine)` same methods as TaskService.
- Restart recovery: tasks persist across instances sharing engine.
- ClickHouse scan: partition by (dataset_id, date), parallelism configurable.

## 4. Testing

- `tests/test_sql_task_service.py`: submit/get/transition/persistence across new instance.
- `tests/test_clickhouse_scan.py`: partition SQL contains PARTITION BY and parallel settings.

## 5. Out of scope

- Prefect (missing dep), full migration.