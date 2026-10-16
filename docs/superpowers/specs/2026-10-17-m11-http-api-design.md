# SynthTrial M11 · HTTP API (FastAPI) Design Spec

> Status: Done
> Date: 2026-10-17
> Scope: T-M11-04 FastAPI service + T-M11-05 PHI redaction hook + T-M11-06 RBAC.

## 1. Problem

P0 只有 CLI (`stctl`). 生产需要 HTTP API 供 SDK/前端调用，且医疗数据永不离脱敏链 (D-4)、租户隔离 (Entra ID + RBAC)。

## 2. Solution

新增 `src/st_platform/api/` 包：
- `app.py`: FastAPI app factory `create_app()` with routers.
- `routes/runs.py`: POST /runs (submit+run eval, returns outcome summary), GET /runs/{task_id}.
- `routes/reports.py`: GET /reports, GET /reports/{hash}.
- `phi.py`: `redact(obj)` 递归脱敏（邮箱/手机号/身份证样例模式）+ `RedactingFilter` 日志过滤器。
- `rbac.py`: `require_role(*roles)` FastAPI dependency; `Role` enum.

In-memory stores reused (TaskService, ReportStore). PHI redaction applied to all persisted payloads via redact before storage? At least logging.

## 3. Contracts

- API key via header `X-API-Key` (dev) mapped to role; production swaps to Entra ID (M11-06 note).
- All responses JSON; errors use HTTPException.
- PHI redaction never raises; returns redacted copy.

## 4. Testing

- `tests/test_api.py`: TestClient smoke: health, submit run, list reports, RBAC 403, PHI redact.

## 5. Out of scope

- Postgres/ClickHouse/Prefect (separate tasks).