# SynthTrial（st-platform v2.0）· 中文版

医疗模型离线评测 P0 核心（中英文双 README）：指标注册表、不可变任务生命周期、配对统计引擎（含 CUPED 与 Bonferroni/Holm/BH）、失败-安全护栏与覆盖度追踪、决策就绪报告、哈希链式审计台账。底层 Go/Python 混合微服务架构。权威需求与架构见 `docs/design.md` + `docs/design_go_python.md`。

- English: [`README.md`](README.md).
- 中文版: 本文件。

---

## 1. 快速开始

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make test            # 运行全部测试
make run             # 端到端演示报告
# 或：
PYTHONPATH=src python3 -m st_platform.cli.stctl demo --n 200 --json
```

## 2. 项目结构

```
src/st_platform/ 各子包：common / registry / audit / dataset / task / inference / infer / safety / report / cli
tests/   91 个测试覆盖所有切片
docs/    需求 + 架构 + superpowers 规格/计划
```

## 3. 协议

MIT 协议（根目录 `LICENSE`）。

如有二次分发，两份 README 请同步更新。
