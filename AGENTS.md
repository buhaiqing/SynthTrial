# SynthTrial · AGENTS.md

> Medical Model A/B Testing & Causal Inference Platform · codename `st-platform`
>
> **状态：仓库尚为空。** 本文当前 100% 是约定与判断，0 条来自代码的事实。
> 代码落地后，把能从代码读到的（目录结构、命令、模块清单）移除，改为指针。
> 需求本身在 `docs/design.md`

---

## 1 · 身份与命名（spine）

| 项 | 值 |
|---|---|
| project_name | `SynthTrial` |
| codename | `st-platform` |
| Python 包前缀 | `st_` |
| 容器 / 镜像 | `st-` |

模块代号 —— 服务与库都用这些短名，对话、代码、日志、看板标题统一：

| 代号 | 覆盖模块 | 一句话职责 |
|---|---|---|
| `st-bucket` | M002 Traffic_Split_Engine | 分流决策：谁进哪一组 |
| `st-infer` | M003 Statistical_Analysis_Engine | 实验结论：这个差异是真效果吗 |
| `st-causal` | M004 Causal_Inference_Module | 无对照组时的效应估计 |
| `st-ledger` | M005 Metrics_Dashboard | 指标口径与证据台账 |
| `st-safety` | M006 Medical_Model_Evaluation | 护栏与模型评测 |
| **`st-lab`** | M001 Experiment_Design_Lifecycle | 实验的创建、灰度、归档 ⚠️ **待确认，见 §5** |

---

## 2 · 核心场景已定：离线评测（2026-10-16 结案）

首批用户的动作：**算法工程师提交待上线模型版本 → 跑离线评测 → 护栏报告 → 决定能否放量。**

由此推出的架构事实：

| 路径 | 形态 | 复杂度归属 |
|---|---|---|
| **离线评测（内核）** | 一次性批量跑完 | M006 + M003 + M005，**唯一的 P0** |
| 在线 A/B（后续） | 长周期实时实验 | M001–M003 在线形态，P1 |

**判据一 · QPS 不适用于本平台。** 离线批任务形态，v1.0 的「千万级 QPS」是误植。平台自己的性能战场是**单集群 TB 级扫描/天**，瓶颈在 I/O 与并行度，不在 QPS。

**判据二 · P0 阶段完全不碰分流服务。** 阶段 0–2 可独立立项、独立交付、不依赖任何在线能力。这是与 v1.0 最大的结构差异。

**判据三 · 场景决定模块边界，不决定优先级。** 场景从「在线实验」改成「离线评测」后，正确动作是重画模块边界，而非重排优先级 —— 后者会留下一堆无人使用的复杂度。推导过程见 `docs/design.md`（§0）

**判据四 · 离线评测原理上测不出三件事**：医生采纳率、诊疗行为的改变、远端健康结局。它们只在一上线后的真实观测里可测 ⇒ **在线层是长期必需，不是可选项**，只是不在第一期。

---

## 3 · 医疗场景的两条正确性铁律

### 3.1 曝光缺口（exposure gap）

**分配 ≠ 曝光。** 用户被分到 B 组（Assignment）和 B 组的结果真的影响了决策（Exposure）是两件事。中间隔着「拿到了没」「拿到了用没用」。

漏记一条 Exposure，该实验的结论就不可信 —— 且这种错误**不会报错**，只会让结论悄悄失真。所以：

- 分流日志与曝光日志分开落，**各自独立可查**
- 结论计算只用 Exposure，Assignment 仅用于分母与偏差校正
- 任何端到端对账，把「有 Assignment 无 Exposure」的比例当成一级指标暴露出来

### 3.2 不可见 ≠ 未曝光

离线侧的同族问题：模型在评测集上高分，**不代表这些样本未参与训练**。污染检测与曝光日志分离是同一条铁律的两个方向，两者都必须有独立机制。污染不会报错，只会让分数虚高且无法察觉。

### 3.3 护栏先于效果

医疗评测里，一个统计显著的收益不构成上线理由，**一个安全底线被击穿则一票否决**。护栏指标与效果指标在报告里**不合并成一个分数**；护栏触发即熔断，熔断判定不等待显著性结论。

---

## 4 · 指标必须可测（measurable）

PRD 里「安全护栏零漏报」按字面无法达成 —— 未知的高危模式无法枚举。直接写进验收标准，会得到一个永远通不过、也永远没人负责的条目。

**规则：每条验收标准都要能写成一句「给定 X，断言 Y，阈值 Z」写进测试。** 写不出来的，按这个模板降级为可承诺的 SLO：

```
「零漏报」  → 「已登记高危模式集 H 的召回率 = 100%；H 之外为未覆盖，
              未覆盖样本数与占比逐实验可审计并随报告输出」
```

同理：
- 「分流一致性 100%」→ 定义为「同一 (业务线, 用户ID, 实验ID, 时间窗) 在**跨地域双活节点**下决策相同」，并给出双活一致性验证方法
- 「统计计算 <3s」→ 声明 P99 还是均值，在哪个数据量级下测
- 「样本量预估误差 <10%」→ 声明依赖「基线转化率估计误差 < X%」，否则该指标不可验收

---

## 5 · 待决事项（不要当成已定）

| # | 问题 | 影响面 | 我的倾向 |
|---|---|---|---|
| Q1 | M001 的代号未分配 | 命名一致性 | `st-lab`（待你确认） |
| Q2 | `st-infer` 与 `st-causal` 语义撞车 —— 前者实为统计显著性检验，后者才是因果推断 | 名字即文档，撞车会持续误导 | M003 改 `st-stats`；**但这是你给的约定，等你裁决** |
| Q3 | ~~首批使用者是谁、第一次打开平台干什么？~~ | ~~整份 PRD 的骨架~~ | ✅ **已结案：离线评测 + 护栏为内核**（2026-10-16，见 §2） |
| Q4 | 标注一致性 κ 的可接受阈值 | 决定结论效力声明 | **需医学/合规方给值，我不拍** |
| Q5 | 护栏红线清单的内容与更新机制 | 决定护栏召回率的定义 | **需合规方给值，我不拍** |

Q3 已解。**Q4/Q5 未解前，M006 护栏的验收标准无法定稿** —— 这两项只有医学与合规方能拍板。

---

## 6 · 指针

- **需求**：`docs/design.md`（权威源，含模块 / 功能 / 验收标准 / 待决事项）
- **任务跟踪**：`docs/tasks.md`（开发进度唯一权威源：M0–M12 milestone + 细粒度 Task）
- **Go+Python 架构**：`docs/design_go_python.md`
- 设计文档：`docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
- 执行计划：`docs/superpowers/plans/`
- 本文只承载**读代码读不到的东西**：约定、判据、取舍理由。目录结构、命令清单、模块签名一律不写在这里 —— 它们属于代码与配置，写在这里只会腐烂。

---

## 7 · 开发纪律（在全局规则之上的本仓追加）

全局 `~/.pi/agent/AGENTS.md`（Cardinal Policy / coding-standard / GCL）是上层权威，本节只追加本仓特有的，**冲突以本节为准**。

| # | 纪律 | 具体 | Why（根因来源） |
|---|---|---|---|
| D-1 | Subagent 模型一致性 | 默认所有 subagent 用 **`opencode-go/deepseek-v4.1-flash`**。该模型 402 欠费期间，**只读评审类 subagent 改用 `minimax-cn/MiniMax-M3`**（用户 2026-10-17 授权）；Generator 仍用主模型。派发前用 models-store 核实 id 存在 | 用户裁定 2026-10-14 + 2026-10-17；`model-fallback.ts` 的 `ALLOWED_TARGETS` 当前仍只白名单那个 402 的模型 |
| D-2 | Spec/Plan 先于 Code | 功能性开发必须先落 `docs/superpowers/specs/` + `docs/superpowers/plans/`，无例外（<5 行 typo 除外） | §Spec+Plan First 铁律 |
| D-3 | 数据不可变 | 提交后的评测任务（标本 + 参数 + 代码版本）冻结为快照，重试产生新任务；已完结结果不可覆盖 | §4.1 可复现性铁律 |
| D-4 | 医疗数据永不离脱敏链 | 任何持久化/传输层必须有 service token + column-level 脱敏钩子；未脱敏数据不得写入日志 | NFR security_compliance + 医疗伦理 |
| D-5 | 零删库 | 任何删除操作必须白名单 + dry-run 默认 + 审计行；「看着像临时产物」不算判据（见 memory 2026-10-16 清理白名单事件） | 不可逆操作红线 |
| D-6 | 护栏先于效果 | 护栏结论不参与效果分数，触发即熔断而不停等显著性；review 时先读护栏 section | §4.2 |
| D-7 | Mutation 在隔离副本 | subagent 做 mutation/反例构造时，强调「只在 `mktemp -d` 副本」+ 列禁写路径 + dispatch 后存 shasum 指纹比对 | 2026-10-16 自复盘 FM（两次踩坑） |
| D-8 | 新增 perf 工作按层判定 | 先声明属于 §1 的哪一层（离线批扫/分流/统计/因果），答不上来不写代码 | §2 判据一 |
| D-9 | 工具钩子会延后改盘 | 判定「某 subagent 越界」前，先 `grep` subagent session 确认写入事实；命中为 0 则 suspect 自身 hook | pi-lens ruff autofix 是 **turn-end deferred**，会在 commit 之后才改盘 → 并行合并期 `git status` 的 `M` 可能是它而非 subagent |
| D-10 | 交接只带 committed state | 在别处（worktree/branch）改完，**必须 commit 后再合入**；合入后 grep 验证该改动真在目标分支上 | 2026-10-16 实测：在 worktree 里改了 4 处却只在 commit message 声称「before merge」，merge 只带 committed state → 缺陷随 push 上线。凡「我改过了」都要 grep 取证 |
| D-11 | 单值断言可能巧合通过 | 断言「两次运行某指标相等」前，先确认两次运行真的不同源；否则挑更宽的断言（全文比对 > 单值比对） | 2026-10-16：变异测试证明 seed A/B 恰好同值时单值断言恒真；且负数场景下 `x < y*0.5` 恒成立。**断言要被变异测试证伪过**才算数 |

### 7.1 纪律 / GCL 协同
- 小于 5 行的 typo/注释/格式化可直接合入主分支，不经 GCL。
- 其余一切变更（含 YAML/运维配置）走 GCL：spec → Generator(经济) → Critic（不同模型盲审；单模型环境下同模型自审必须在交付说明标「自审、独立性受限」）。
- GCL 每轮 Critic 的 finding 修复后追加到 `docs/self-review-playbook.md`（防复发）。

---

## 8 · 业界常用工具链

### 8.1 后端 / 数据
| 层 | 主选 | 备选/说明 |
|---|---|---|
| 语言 | Python 3.12+ | Java (Quarkus) / Go (on 部分高 QPS 流) |
| Web 框架 | FastAPI + Uvicorn | Starlette, gRPC（`st-bucket` 在线期） |
| 校验 / 序列化 | Pydantic v2 | OpenAPI schema-first |
| 数据处理 | Pandas / Polars（Polars 优先，TB 级） | Arrow 共享 memory |
| 统计库 | **statsmodels**（配对 t / McNemar / CUPED / 因果回溯） | scipy.stats（基础）、pingouin（配对 effect size） |
| 科学计算 | NumPy / SciPy | — |
| 因果库 | DoWhy / EconML（仅 P2） | CausalML |
| ORM / 查询 | SQLAlchemy 2 + Alembic | asyncpg 直读 OLAP |

### 8.2 数据 / 基础设施
| 组件 | 选型 | Why |
|---|---|---|
| 主存 | PostgreSQL（metadata/注册表/审计账本） | ACID、可不可变表 design |
| OLAP | **ClickHouse** | TB 级 batch 扫描、partitioning、Materialized view | 
| 缓存 | Redis（`st-bucket` 一致性桶 / 护栏计数器） | milliseconds 级读 |
| 消息 | Kafka（exposure/assignment 日志） | 至少一次 + 幂等 consumer |
| 对象存储 | S3-compatible（模型 artifact/报告） | immutable write + lifecycle |
| 编排 | Prefect / Dagster（评测任务 DAG） | 可重试 + 可视化 |
<|constrain|> 编排 | Airflow（已有基建就绪时） | 

### 8.3 可观测 / 评测
| 层 | 选型 | 用途 |
|---|---|---|
| LLM / 模型 tracing | **Langfuse** | 评测链路、token 利用、prompt 版本 |
| 应用 tracing | OpenTelemetry + Tempo | 跨服务 trace |
| logging | structured JSON (loguru/python-json-logger) | 审计可解析 |
| metrics | Prometheus + Grafana | SLO 看板 |
| quality grader | OpenTelemetry trace → Langfuse eval | 护栏回归 |

### 8.4 质量 / 工程
| 检查 | 命令 | 门禁 |
|---|---|---|
| Lint | `ruff check --fix && ruff check` | 零 error |
| Type | Pyright / mypy strict | 零 error（碰过的文件）|
| Format | Ruff format / Black | CI enforce |
| 测试 | `pytest -v` 全部 pass（<|constrain|>预存 failures 显式说明） | green |
| 安全 | Bandit（Python）、Trivy（镜像） | S1/S2 zero |
| 依赖 | `pip-audit` / `dependabot` | 分期升级 |
| Doc drift | `check_doc_sync.py` | 每 PR |

### 8.5 医疗 / 评测生态
| 项 | 工具 | 备注 |
|---|---|---|
| 医疗 NLP | scispaCy / medSpacy / 大语言模型-derived embeddings | 带版本锁死 |
| 医学本体 | UMLS / ICD-10 + ICD-11 | 不直接嵌 DB，做 external vocab lookup |
| 安全分类 | `st-safety` 自研规则集 + ML 分类器 | 阈值由合规方给（Q5） |
| PHI redaction | 无标 HIPAA-PII scanner + 定制 term list | 双层，不可单 rely 单一 |
| labeling QA | Label Studio / LabelBox + κ dashboard | 每 labeled subset 要报 κ |

---

## 9 · 技术架构选型（关键决定理由）

<|constrain|> # | 决定 | 选项取舍 | 一句话 why |
|---|---|---|---|
| A-1 | **有状态 OLAP**：PostgreSQL → ClickHouse | 非 trivially SQL where Postgres handles metadata & registry<|constrain|>*OLAP* handles TB scanning; don't try one tool both | Split responsibility by read pattern, not by scale |
| A-2 | 批处理 orchestrator = **Prefect / Dagster**，非 Airflow | Airflow legacy UI vs modern API/notebook | Prefect db-less 部署更轻；有 Airflow 基建时保留兼容 |
| A-3 | 统计内核 = **statsmodels + scipy**，非 sklearn | sklearn 只有 generic estimator | statsmodels 有配对/McNemar/CUPED/BH，sklearn 没有 |
| A-4 | 评测任务 = **不可变 immutable batch**，CLI 可重跑但写只追加 | 在线实验/A/B 那套 NOISY | 版本链 Complete == reproducibility |
| A-5 | 结果持久化 = **append-only + content-addressed blob id** | edit/delete 的 TB scan 错报 6 walks | 公式：content_id = sha256(config ⊕ inputs)； same hash = same result |
| A-6 | 配置 = **Python 为 primary, Go 仅 for `st-bucket` 在线期** | 统一(dev experience,ML ecosystem) ↔ 性能(edge routing,split) | 很难在 Python 3.12 / PyPy 路径上压到 1ms SLA，所以 split at routing layer |
| A-7 | 鉴权 / 租户 = **Entra ID (Azure AD) + RBAC** | internal IdP over Keycloak | 医疗数据合规要求 IdP 有 certification; reuse 已采购 |
| A-8 | 报告 / 导出 = **server-side render（PDF via WeasyPrint）+ 导出 Markdown** | FP 6.5 client-side | PHI 保证不离开 gateway |
| A-9 | Result cache = **per-task hash，不是全局 idempotency key** | 全局 TTL 误以为 deterministic | evaluation deterministic by input，so per-task cache 无 TTL ； global 需 cache invalidation stair 2% error |
| A-10 | **分网（n-to-n）+ off-row override**：PII 源与模型探<|constrain|>ors 指标 store on separate VLAN | single net 就 leakage 1 path | latest zero-PII tier/**patient-data tier**/**model-tier** 三网，admin gateway only |

### 9.1 因果推断进入的触发条件
P2（st-causal）启动时必须同时满足：
- 已完成的 P0 报告 ≥ 50 份（证据）
- ≥ 3 个 bucket 过去偏差 ≥ 10pp（real-world off-line divergence 现象）
- 合规团队能给 approval 证明（证据链）
否则不啟动。

---

## 10 · 部署形态（回答“前端/后端？Go 还是 Python？”）

### 10.1 它不是普通的前后端 SaaS
<|constrain|> 行 | 说明 |
|---|---|
| 用户 | 算法/评测工程师 + reviewer/合规（月活跃极低） |
| 负载 | TB 级 batch 扫描 + 单机 EVAL 任务 |
| 延迟敏感性 | **无**（4h 级）；可承受 batch 任务队列 |
| 面向 | CLI + SDK + Web reports dashboard |

这意味着：**frontend 只做 artifact viewer（看报告），不是交互式 app。**

### 10.2 服务端形態（pattern）
| 形态 | 适用 | 评语 |
|---|---|---|
| **Type A · Python monolith（MVP）** | Phase 0–2 | 指标注册表 + ClickHouse + Prefect + FastAPI；80% 价值，最低运维 |
| **Type B · dual-runtime (gold)** | P1 起 | Go 控制面（st-bucket / st-ledger + scheduler） + Python 评测 sidecar（FastAPI / gRPC）+ 共享 Prefect DAG |
| **Type C · full mesh** | >10x TB/day | 避免，拟议进入 orthogonal optimization 不去 premature |

### 10.3 语言 split 原則
- **Python**： 数据语义、因果(statsmodels/DoWhy)、metadata、audit  ( domain-heavy, change infrequently )
- **Go**： **只有**在 QPS / p99 真要求 sub-ms 时：st-bucket 在线分流、st-ledger routing + 指标聚合 ( CPU-bound). **Go 并非加速 ML，只是 tail-latency guarantee**.
- **追加 V8 iso-core**： 为了 consistent tarball，所有 service 共 registry schema (Protobuf JSONTag -> Pydantic) — interface is rngned only once.

### 10.4 D ث（simplicity）
- 不混入 **新的语言/组件**，除非 workload 原语 justified.
- A only wins in Phase 0-2. 失败模式：把 Type B 升到 Type C premature 在 TB 增长（"Big Data Fallacy"）— 只有 10TB/day 时先 scale 硬件再 refactor service.
- 任何 ≥ 3 months change 的 ADR 必须在 `./docs/adr/` （ADR 元数据：decision-date, decider, reversal-cost）.

### 10.3 _REF_：Python ↔ Go 边界
- 通过 Protobuf canonical schema 作合同（OpenAPI 用 gen tool 生成）
- Go ↔ Python 通信： **mTLS gRPC** on Kubernetes ( internal cluster only )
- Python → ClickHouse： **Apache Arrow Flight** ( 避免 row-based 导入 )
- 失败模式：直接 wire HTTP encode (json dumps) 在 TB scan 时 = **biggest latency pitfall**，必须 avoid。