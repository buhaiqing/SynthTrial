# SynthTrial (st-platform v2.0)

Bilingual medical model offline evaluation P0 core: metric registry, immutable task lifecycle, paired statistical engine (with CUPED + Bonferroni/Holm/BH), fail-closed safety redlines, hidden-state coverage accountability, decision-ready report, and hash-linked audit ledger. Go/Python hybrid microservice architecture. See `docs/design.md` + `docs/design_go_python.md` for the definitive requirements and architecture.

- English: this file.
- 中文版: [`README.zh.md`](README.zh.md).

---

## 1. Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make test            # run all tests
make run             # end-to-end demo report
# or:
PYTHONPATH=src python3 -m st_platform.cli.stctl demo --n 200 --json
```

## 2. Project layout

```
src/st_platform/ st_platform.* packages
├── common/      registry / audit / dataset / task / inference / infer / safety / report / cli
tests/ 215 tests across all slices
docs/  requirements + architecture + superpowers specs/plans
```

## 3. License

MIT (see `LICENSE`).

English README (canonical) and Chinese README are maintained together — both shipped. If you fork, keep both in sync.
