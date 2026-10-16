# SynthTrial M9 · P1 上线放量 · st-bucket Design Spec

> Status: Done
> Date: 2026-10-17
> Scope: T-M9-01 (deterministic bucketing) + T-M9-02 (cross-region consistency verification)
> Out of scope: gray release (T-M9-03), Assignment/Exposure separation (T-M9-04), st-lab (T-M9-05), shadow mode (Q6).

## 1. Problem

P1 需要确定性分流：同一 `(business_line, user_id, experiment_id)` 在跨地域双活节点下必须落入同一组。当前仓库无 st-bucket 模块；需要可验证的一致性脚本。

## 2. Solution

- 新增 `src/st_platform/bucket/` 包，提供 `bucket(user_id, experiment_id, salt, n_buckets)` 使用 MurmurHash3 (32-bit) 确定性分桶。
- 提供 CLI/脚本 `tools/verify_bucket_consistency.py`，在两个独立进程/种子下比对分桶结果，输出一致性报告与 exit code。

## 3. Contracts

- `bucket(...)` 纯函数，无全局状态，输入相同输出相同。
- Hash 输入拼接 `f"{business_line}|{user_id}|{experiment_id}|{salt}"`。
- n_buckets 默认 2（A/B），支持 2..100。
- 一致性脚本接受 `--samples N`，生成 N 个合成用户，分别在两个子进程（不同 PYTHONHASHSEED）运行分桶，比较分组；任一不一致 exit 1。

## 4. Testing

- `tests/test_bucket.py`: 同输入跨调用同组；不同用户分布；n_buckets 边界。
- 一致性脚本冒烟：N=1000，exit 0。

## 5. Out of scope

- 灰度放量、Assignment/Exposure、正交实验、shadow mode。