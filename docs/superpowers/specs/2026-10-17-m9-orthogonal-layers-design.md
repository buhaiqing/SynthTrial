# SynthTrial M9 · T-M9-06 正交/多层实验架构 Design Spec

> Status: Done
> Date: 2026-10-17
> Scope: T-M9-06 orthogonal / multi-layer experiment architecture.

## 1. Problem

P1 在线实验需要同时跑多个实验（UI、排序、定价等）而不互相污染。同一用户在**同一层**内只能落入一个实验（互斥），**跨层**独立（正交）。当前 `st-bucket` 只有单实验 `bucket()`，没有层/互斥/正交概念。

## 2. Solution

新增 `src/st_platform/bucket/layers.py`：

- `Experiment(experiment_id, layer_id, weight=1)`：实验定义，weight 为层内流量权重。
- `Layer(layer_id, experiments)`：层，层内实验互斥。
- `assign(user_id, layers, *, business_line, base_salt)`：返回 `{layer_id: experiment_id | None}`，每层最多一个实验；跨层独立。
- 底层用 `murmur3_32` 对 `business_line|user_id|layer_id|base_salt` 取模总权重，映射到实验。

## 3. Contracts

- 纯函数，无全局状态，确定性。
- 同一 `(user_id, layer)` 跨调用/进程结果一致。
- 同一层：同一用户永远落入至多一个实验（互斥）。
- 跨层：不同 layer_id 使用不同哈希输入，正交（独立）。
- 空层 / 无实验 → `None`。
- weight 必须正整数；layer_id/experiment_id 非空。

## 4. Testing

- `tests/test_layers.py`：确定性、互斥、正交、空层、权重分布、边界。

## 5. Out of scope

- 灰度百分比（RolloutController 已覆盖）、Assignment/Exposure（exposure 模块）、持久化。