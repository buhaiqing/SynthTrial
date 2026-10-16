# SynthTrial M10 · Causal Inference (P2) Design Spec

> Status: Done
> Date: 2026-10-17
> Scope: T-M10-02 DiD + parallel trends; T-M10-04 RDD/PSM (initial subset).

## 1. Problem

P2 因果推断在触发条件满足后启动。提供算法库：DiD（含平行趋势检验）、RDD、PSM。

## 2. Solution

新增 `src/st_platform/causal/`：
- `did.py`: `difference_in_differences(outcomes, treated, post)` + `parallel_trends_test(panel)`。
- `rdd.py`: `regression_discontinuity(x, y, cutoff)` local linear.
- `psm.py`: `propensity_score_match(treated_df, control_df, covariates)`.

## 3. Contracts

- 纯函数/类，输入 pandas DataFrame 或 arrays，输出 dict with estimate, se, p_value, ci.
- 无外部因果库依赖（DoWhy 未安装）；使用 statsmodels/numpy/pandas。

## 4. Testing

- `tests/test_causal_did.py`, `tests/test_causal_rdd.py`.

## 5. Out of scope

- Synthetic control, IV, ITS (后续)。