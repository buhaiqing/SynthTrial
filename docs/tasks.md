# SynthTrial 开发任务跟踪（tasks.md）

> codename `st-platform` · 本文件是**开发进度的唯一权威源**（AGENTS.md CP-6）。
> 需求在 [`design.md`](design.md)，运维在 [`RUNBOOK.md`](RUNBOOK.md)，架构在 [`ARCHITECTURE.md`](ARCHITECTURE.md)。
> 防复发记录在 [`self-review-playbook.md`](self-review-playbook.md)。
>
> **维护规则**
> 1. 每个 Task 的「验收」必须是一条**可执行命令**，不是描述（AGENTS.md §4）。
> 2. 状态只有四种：`✅ 已完成` / `⬜ 待做` / `⛔ 被阻塞` / `🔧 进行中`。不用百分比。
> 3. 完成一个 Task 就勾选并补 commit sha —— 没证据的 ✅ 不算完成（NO EVIDENCE = NOT COMPLETE）。
> 4. 新增 Task 必须挂在某个 Milestone 下；没有归属的 Task 不进本文件。

---

## 进度总览

| Milestone | 内容 | 状态 |
|---|---|---|
| [M0](#m0)需求与设计基线) | 需求、设计、架构、纪律基线 | ✅ |
| [M1](#m1)领域地基) | common / registry / audit / dataset | ✅ |
| [M2](#m2)任务生命周期与推理) | task / inference | ✅ |
| [M3](#m3)统计引擎) | infer（配对检验 · 效应量 · CUPED · 多重校正） | ✅ |
| [M4](#m4)护栏与报告) | safety / report | ✅ |
| [M5](#m5)结果存储) | store（内容寻址、只追加） | ✅ |
| [M6](#m6)评测管线) | evaluation（P0 纵向切片） | ✅ 代码完成，未接线 |
| [M7](#m7)端到端接线--正确性收口) | **接线 + 4 项正确性缺口** | 🔧 进行中 |
| [M8](#m8)文档与依赖图) | mermaid 图 / RUNBOOK / ARCHITECTURE / playbook | ✅ |
| [M9](#m9)p1-上线放量) | st-bucket / st-lab | ⬜ |
| [M10](#m10)p2-因果推断) | st-causal | ⬜ |
| [M11](#m11)生产基建) | Postgres / ClickHouse / Prefect / HTTP API | ⬜ |
| [M12](#m12)需人拍板) | Q1·Q2·Q4·Q5·Q6 | ⛔ |

**基线：** 154 tests · 4,663 LOC · 33 modules · 0 TODO markers · `origin/main` = `9aaa008`

---

<a id="m0"></a>

## M0 · 需求与设计基线 ✅

| ID | Task | 验收 | 证据 |
|---|---|---|---|
| T-M0-01 | 确认核心场景 = 离线评测 + 护栏为内核 | `grep -n "离线评测" docs/design.md` | `design.md` §2 |
| T-M0-02 | 重画模块边界（而非重排优先级） | `grep -c "^### M00" docs/design.md` → 6 | `design.md` §3 |
| T-M0-03 | 指标可测性降级规范（"零漏报" → SLO） | `grep -n "降级为可承诺 SLO" docs/design.md` | `design.md` §7 |
| T-M0-04 | Go+Python 架构与数据流 | `test -f docs/design_go_python.md` | 169 行 |
| T-M0-05 | 项目纪律（含 D-1…D-11） | `grep -c "\| D-" AGENTS.md` → 11 | `AGENTS.md` §7 |
| T-M0-06 | 中英双语 README + MIT | `test -f README.zh.md && head -1 LICENSE \| grep -q MIT` | `eadf5a7` |

---

<a id="m1"></a>

## M1 · 领域地基 ✅

| ID | Task | 验收 | 证据 |
|---|---|---|---|
| T-M1-01 | 不可变基类 + sha256 + verdict 枚举 | `PYTHONPATH=src python3 -c "from st_platform.common.types import Versioned"` | `21eabd3` |
| T-M1-02 | 指标注册表（版本递增、只追加历史） | `pytest -q tests/test_registry.py` | 5 passed |
| T-M1-03 | 哈希链式审计台账 | `pytest -q tests/test_audit.py` | 3 passed |
| T-M1-04 | 数据集模型 + 污染检测 | `pytest -q tests/test_dataset.py` | 4 passed |
| T-M1-05 | **深冻结 params**（阻断 content_hash 漂移） | `pytest -q tests/test_task.py -k freeze` | `12ed565` |

---

<a id="m2"></a>

## M2 · 任务生命周期与推理 ✅

| ID | Task | 验收 | 证据 |
|---|---|---|---|
| T-M2-01 | 显式状态机（`ALLOWED_TRANSITIONS`） | `pytest -q tests/test_task.py` | 20 passed |
| T-M2-02 | content_hash 为计算字段（永不错位） | `grep -n "computed_field" src/st_platform/task/models.py` | `eb247b8` |
| T-M2-03 | retry 生成新 task_id，不覆盖父任务 | `pytest -q tests/test_task.py -k retry` | `8eff52d` |
| T-M2-04 | MockRunner 跨进程确定性（sha256 播种） | `PYTHONHASHSEED=0/99991 ... run_batch` → 分数一致 | 已验证 |
| T-M2-05 | 重试/别名泄漏防护 | `pytest -q tests/test_task.py -k "isolated or shares"` | `12ed565` |

---

<a id="m3"></a>

## M3 · 统计引擎 ✅

| ID | Task | 验收 | 证据 |
|---|---|---|---|
| T-M3-01 | 配对 t / Wilcoxon / McNemar | `pytest -q tests/test_paired.py` | `7f3f576` |
| T-M3-02 | 效应量 + CI | `pytest -q tests/test_effect.py` | 11 passed |
| T-M3-03 | **relative lift CI 改 delta method** | `pytest -q tests/test_effect.py -k naive` | `1112684` |
| T-M3-04 | CUPED（零方差拒绝） | `pytest -q tests/test_cuped.py` | — |
| T-M3-05 | 多重校正 Bonferroni/Holm/BH | `pytest -q tests/test_multicorrect.py` | — |
| T-M3-06 | McNemar Yates 校正 + 全一致显式处理 | `grep -n "continuity" src/st_platform/infer/paired.py` | `698881f` |
| T-M3-07 | CUPED 泄漏护栏（协变量不得等于处理后指标） | `pytest -q tests/test_cuped.py -k covariate` | `698881f` |
| T-M3-08 | 退化输入不得产出 NaN | `pytest -q tests/test_paired.py -k degenerate` | `12ed565` |

> T-M3-03 的临床判据：naive CI 在 rate-0.15 fixture 上给出 `[+0.28, +3.05]`（不含 0，读作"显著提升"），
> 而 honest CI 为 `[-0.95, +4.28]`（跨 0，无法排除无效）。守卫断言的是这个临床性质，不是宽度比。

---

<a id="m4"></a>

## M4 · 护栏与报告 ✅

| ID | Task | 验收 | 证据 |
|---|---|---|---|
| T-M4-01 | 红线规则集 + 三档裁决 | `pytest -q tests/test_safety.py` | `8e83256` |
| T-M4-02 | BLOCK 一票否决（不可被下游覆盖） | `pytest -q tests/test_safety.py -k block` | — |
| T-M4-03 | **未注册 rule id 失败关闭（BLOCK）** | `python3 -c "…check({'ghost':True}).tier"` → `BLOCK` | `e372daf` |
| T-M4-04 | 覆盖度诚实披露（uncovered count/ratio） | `grep -n "Recall (known risks)" src/st_platform/report/report.py` | `e372daf` |
| T-M4-05 | 可复现 5 要素校验（缺一即拒） | `pytest -q tests/test_report.py -k validate` | — |
| T-M4-06 | 护栏与效果分离渲染 | `pytest -q tests/test_report.py -k basic` | — |

---

<a id="m5"></a>

## M5 · 结果存储 ✅

| ID | Task | 验收 | 证据 |
|---|---|---|---|
| T-M5-01 | 内容寻址存储（sha256 = 幂等键） | `pytest -q tests/test_store.py` | 8 passed |
| T-M5-02 | 只追加：地址冲突拒绝且不覆盖 | `pytest -q tests/test_store.py -k append_only` | — |
| T-M5-03 | write-then-rename（不留半写文件） | `grep -n "os.replace" src/st_platform/store.py` | — |
| T-M5-04 | 损坏条目必须暴露而非隐藏 | `pytest -q tests/test_store.py` | — |

---

<a id="m6"></a>

## M6 · 评测管线 ✅（代码完成，未接线）

| ID | Task | 验收 | 证据 |
|---|---|---|---|
| T-M6-01 | 管线骨架：配对跑批 → 统计 → 护栏 → 渲染 → 存储 | `pytest -q tests/test_evaluation_pipeline.py` | `203c381` |
| T-M6-02 | 多重校正在管线内强制 | `grep -n "assert_correction_applied" src/st_platform/evaluation/pipeline.py` | `pipeline.py:177` |
| T-M6-03 | `promotable` 仅 PASS 为真（WARN 需人工审批） | `pytest -q tests/test_evaluation_pipeline.py -k promotable` | — |
| T-M6-04 | case_id 不对齐即拒绝 | `pytest -q tests/test_evaluation_pipeline.py -k case` | — |
| T-M6-05 | 相同输入产出相同 report_hash | `pytest -q tests/test_evaluation_pipeline.py -k hash` | — |

> **⚠️ 缺口：无任何调用方。** `grep -rn "EvaluationPipeline" src/st_platform/cli/` → 无。
> 管线能力已测试但未上任何端到端路径 → 见 M7。

---

<a id="m7"></a>

## M7 · 端到端接线 + 正确性收口 🔧

> **主 Agent 直做，不再派 subagent。** 顺序有依赖：T-M7-01 必须先做，它会连带关闭 T-M7-04/05/06。

| ID | Task | 验收 | 阻塞于 | 状态 |
|---|---|---|---|---|
| T-M7-01 | **`stctl run` 接上 `EvaluationPipeline`** | `PYTHONPATH=src python3 -m st_platform.cli.stctl run --dataset d --model m` 产出报告并落盘 | — | 🔧 |
| T-M7-02 | 报告接入**真实 CI**（替换 `ci_low=0.0/ci_high=1.0`） | `grep -c "ci_low=0.0" src/st_platform/cli/stctl.py` → 0 | — | ⬜ |
| T-M7-03 | demo 路径也强制多重校正 | `grep -n "assert_correction_applied" src/st_platform/cli/stctl.py` | — | ⬜ |
| T-M7-04 | 失败路径转 `FAILED` | `pytest -q tests/test_cli_run.py -k failure` | T-M7-01 | ⬜ |
| T-M7-05 | 端到端落盘后可 `stctl reports` 列出 | `stctl run … && stctl reports` 可见新条目 | T-M7-01 | ⬜ |
| T-M7-06 | demo 的污染检测不再恒为空集 | `grep -n "contamination_detect(ds, set())" src/st_platform/cli/stctl.py` → 无 | — | ⬜ |
| T-M7-07 | `contamination_result` 纳入必填可复现要素 | `pytest -q tests/test_report.py -k contamination` | **需用户确认破坏性变更** | ⛔ |
| T-M7-08 | 修 `ARCHITECTURE.md:41` cli→store 漂移 | `grep -n "not.*task.*,.*store" docs/ARCHITECTURE.md` → 无 | — | ⬜ |
| T-M7-09 | 修 design §11.1 自相矛盾（"st-bucket 一次都不出现"但图中出现 4 次） | 人工复核该段 | — | ⬜ |
| T-M7-10 | CI 门禁接入 `gen_dep_graph.py --check` | `.github/workflows/*.yml` 存在该 step | — | ⬜ |

**T-M7-07 说明：** 把 `contamination_result` 加入必填会让**现有全部报告失效**（破坏性）。
design.md §4.1 要求它属于五要素，但实现只校验 5 项中的 4 项 + seed。这是设计与实现的真实分歧，
不是我擅自能定的 → 已标 ⛔。

---

<a id="m9"></a>

## M9 · P1 上线放量 ⬜

> 触发条件：P0 阶段 0–2 交付且业务方确认需要在线验证。

| ID | Task | 验收 | 依赖 |
|---|---|---|---|
| T-M9-01 | `st-bucket` 确定性分桶（MurmurHash） | 同 (user, exp) 跨进程同组 | Q6 |
| T-M9-02 | 一致性验证方法（跨地域双活） | 给出可执行一致性验证脚本 | — |
| T-M9-03 | 灰度放量 10%→50%→100% | 调整生效 < 1s | T-M9-01 |
| T-M9-04 | **Assignment / Exposure 分离**（design §4.3，P1 最高优先级） | 端到端对账暴露"有 A 无 E"比例 | T-M9-01 |
| T-M9-05 | `st-lab` 任务编排与配额 | — | T-M7-01 |
| T-M9-06 | 正交/多层实验架构 | — | P2 决策 |

---

<a id="m10"></a>

## M10 · P2 因果推断 ⬜

> **触发条件（design M004，三条全满足才启动）：**
> ① 已完成 P0 报告 ≥ 50 份 ② ≥ 3 个 bucket 历史偏差 ≥ 10pp ③ 合规团队可给 approval 证明

| ID | Task | 验收 | 状态 |
|---|---|---|---|
| T-M10-01 | 触发条件核验（三条全满足） | 逐条给出证据 | ⬜ |
| T-M10-02 | DiD（含平行趋势检验） | 平行趋势自动化检验 | ⬜ |
| T-M10-03 | Synthetic Control | — | ⬜ |
| T-M10-04 | RDD / PSM / IV / ITS | 至少 5 种算法 | ⬜ |

---

<a id="m11"></a>

## M11 · 生产基建 ⬜

> 当前 P0 全内存 + 本地 JSON。本层决定能否上生产。

| ID | Task | 验收 | 状态 |
|---|---|---|---|
| T-M11-01 | Postgres 替换内存 TaskService（契约不变） | 重启后任务可恢复 | ⬜ |
| T-M11-02 | ClickHouse 接 TB 级扫描 | 分区策略 + 并行度基准 | ⬜ |
| T-M11-03 | Prefect/Dagster 编排 | 失败可重试、可视化 | ⬜ |
| T-M11-04 | HTTP API（FastAPI） | — | ⬜ |
| T-M11-05 | PHI 脱敏钩子（D-4：永不离脱敏链） | 持久化/传输层均有钩子 | ⬜ |
| T-M11-06 | 鉴权与租户隔离（Entra ID + RBAC） | — | ⬜ |

---

<a id="m12"></a>

## M12 · 需人拍板 ⛔

> 我不猜这些值。任何依赖它们的 Task 都不得开工（AGENTS.md §5「我不拍」）。

| ID | 问题 | 阻塞 | 我的倾向 | 状态 |
|---|---|---|---|---|
| T-M12-01 | **Q4** 标注一致性 κ 可接受阈值 | M006 F2 结论效力声明 | 需医学方给值 | ⛔ |
| T-M12-02 | **Q5** 护栏红线清单 R 的内容与更新机制 | M006 F4 召回率定义、护栏验收标准定稿 | 需合规方给值 | ⛔ |
| T-M12-03 | **Q2** `st-infer` vs `st-causal` 命名撞车 | 命名一致性 | M003 改 `st-stats` | ⛔ |
| T-M12-04 | **Q1** M001 代号 | 命名一致性 | `st-lab` | ⛔ |
| T-M12-05 | **Q6** 是否需影子模式（新旧模型同时在线） | M002 是否提前到 P0 | 倾向 P1 | ⛔ |
| T-M12-06 | T-M7-07 破坏性变更是否接受 | 全部现有报告失效 | 待裁决 | ⛔ |

---

## 附录 · 本项目已修复的真实缺陷

完整记录见 [`self-review-playbook.md`](self-review-playbook.md)。摘要（每条都有测试或命令做守卫）：

| 类别 | 缺陷 | 守卫 |
|---|---|---|
| 统计 | relative lift CI 用抽样均值当常数 → 区间永远偏窄，罕见不良事件下偏离 46× | `test_effect.py -k naive` |
| 统计 | `paired_t_test` 对 n=1 / 零方差返回全 NaN | `test_paired.py -k degenerate` |
| 统计 | 退化输入返回零宽区间（假确定性） | `test_effect.py -k single_pair` |
| 正确性 | pydantic `frozen=True` 不阻止嵌套容器原地修改 → content_hash 漂移 | `test_task.py -k freeze` |
| 可复现 | 用 `hash()` 播种 → 同输入每次报告数字不同（6 个 seed 6 个结果） | `test_cli_reproducibility.py` |
| 安全 | 未注册 rule id 命中被降级为 PASS | `test_safety.py` + evidence 探针 |
| 文档 | 图里画了不存在的 import 边（手绘图静默漂移） | `tools/gen_dep_graph.py --check` |
| 流程 | worktree 里的修复未 commit → merge 只带 committed state，缺陷随 push 上线 | AGENTS.md D-10 |
| 流程 | 并行开发致文档在合并时过期 | playbook row 12 |
