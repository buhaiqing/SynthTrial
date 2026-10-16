# SynthTrial · Mutation Testing Log

> 变异测试执行轨迹记录。每条记录：日期、目标、变异操作、命令、结果（killed/survived）、发现的问题、守卫/commit。
> 目的：可回答“执行了哪些变异测试、因为什么问题、发现了什么”。

| # | 日期 | 目标代码 | 变异操作 | 执行命令 | 结果 | 发现的问题 | 守卫 / commit |
|---|---|---|---|---|---|---|---|
| M-1 | 2026-10-16 | `cli/stctl.py::_digest` | 回退为 `hash()` 播种 | `PYTHONHASHSEED=0/1 stctl demo --n 40` 对比全文 | survived（暴露缺陷） | 相同输入 6 种 seed 产出 6 种报告 | `sha256_hex(row["case_id"])` / `12ed565` |
| M-2 | 2026-10-16 | `tests/test_cli_reproducibility.py` 单值断言 | 哈希种子巧合使单值相等 | mutation 验证 | survived（暴露缺陷） | 单值断言无法检测差异 | 全文比对 + D-11 / `8ab2a48` |
| M-3 | 2026-10-16 | `task/models.py::_deep_freeze_params` | 关闭深冻结 | `t.params["k"]=9` | survived（暴露缺陷） | hash 从 `50c50ed6…` 漂移到 `e5cc839b…` | `common/freeze.py` / `12ed565` |
| M-4 | 2026-10-17 | demo 污染守卫断言 | 签名集 `rows[:3]` → `rows[3:]`（37 条） | `pytest -k contamination` | survived（暴露缺陷） | `"train_overlap_count=3" in out` 仍通过（前缀匹配） | 边界断言 / `9f9e8be` |
| M-5 | 2026-10-17 | `infer/effect.py::relative_lift_ci95` | 回退为除以 `before_mean` | `pytest -q tests/test_effect.py -k naive` | survived（暴露缺陷） | CI 过窄、把无效读作显著 | delta method / `1112684` |

> 说明：以上为手工变异（mutant-by-hand），非自动化工具运行。自动化 mutation 门禁尚未接入（见 AGENTS.md §7.1 要求）。