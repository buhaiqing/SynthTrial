# SynthTrial Architecture Notes (st-platform P0)

> For someone adding their first module. **What to build** lives in `docs/design.md`
> (requirements) and `docs/design_go_python.md` (target topology); those are the
> single sources of truth for requirements and must not be restated here
> (`AGENTS.md` CP-6). This file records only what the code does **today**:
> dependency direction, the invariants, and the file+symbol that enforces each one.
>
> Verified against commit `eb247b8`, Python 3.12.1, `114 passed`.

---

## 1 · Package map and dependency direction

Direction (real, read off the imports — `grep -rn "^from st_platform" src/ --include=*.py`)
is a strict DAG, not a layering convention:

```text
common/            <- the root: imports nothing from st_platform
├── leaves (import only common/, or nothing at all)
│     dataset/  registry/  audit/  infer/  inference/  store.py
├── safety/        -> common/ (+ safety.* within the package)
├── report/        -> common/, safety.coverage
├── task/          -> common/ (+ dataset.core in service.py, for the Dataset type)
└── cli/           -> audit, common, dataset, infer, registry, report, safety  (composition root)
                     nothing imports cli/
```

| Package | Modules | May import from `st_platform.*` | Owns |
|---|---|---|---|
| `common` | `types.py` (`Versioned`, `sha256_hex`, `utcnow`, `SafetyVerdictTier`), `freeze.py` (`FrozenDict`, `freeze`) | — (stdlib + pydantic only) | hashing, base model config, deep freeze |
| `audit` | `ledger.py` | — (stdlib only) | hash-linked append-only event chain |
| `dataset` | `core.py` (`Dataset`, `DatasetSplit`, `case_signature`, `contamination_detect`) | `common.types` | dataset snapshot + contamination evidence |
| `registry` | `metrics.py` (`MetricDefinition`, `MetricRegistry`) | `common.types` | metric definitions, versioned |
| `infer` | `paired.py`, `effect.py`, `cuped.py`, `multicorrect.py`, `result.py` | **none** (numpy/scipy/statsmodels only) | paired tests, effect sizes, correction |
| `inference` | `runner.py` (`ModelRunner`, `MockRunner`, `run_batch`) | `common.types` | the model-execution seam (see §1.2) |
| `safety` | `rules.py`, `checker.py`, `coverage.py` | `common.types`, `safety.*` (intra-package) | redline set, 3-tier verdict, coverage |
| `report` | `report.py` (`ReportRenderer`, `ReproducibilityMeta`) | `common.types`, `safety.coverage` | markdown rendering, reproducibility gate |
| `task` | `models.py`, `service.py` | `common.types`, `common.freeze`, `dataset.core` (in `service.py`, for the `Dataset` type) | immutable snapshot + lifecycle |
| `store.py` | `ReportStore` | `common.types` | content-addressed append-only artifact store |
| `cli` | `stctl.py` | `audit`, `common`, `dataset`, `infer`, `registry`, `report`, `safety` — **not** `task`, `store`, `inference` | the only place that wires multiple domains together |

**Rules a reviewer can enforce from this table**

1. `common/` is the root and imports no sibling. A new "shared" helper that needs
   a domain type belongs in that domain, not in `common/`.
2. Leaf domains (`dataset`, `registry`, `audit`, `infer`, `inference`, `store`) never
   import each other.
3. `safety/` and `report/` do **not** import `infer/`. `ReportRenderer` consumes
   duck-typed objects (`getattr(r, "test_name", ...)`), so a new statistic type
   needs no change on the reporting side.
4. `task/` has no importer outside its own package today (`grep -rn "st_platform.task" src/` → only
   `task/service.py` and `task/__init__.py`); the CLI does not exercise the lifecycle. If reporting
   starts to need task state, pass the value in rather than importing `task` from a domain package.
5. `cli/` is the composition root: if you find yourself importing a domain from
   another domain to make a script work, put the wiring in the CLI instead.
6. There are no cycles today. If a change seems to need one, the missing thing is a
   seam (a protocol or a plain value), not an import.

### 1.2 The one naming trap

`infer/` and `inference/` are different things:

| Package | Meaning | Consumed by |
|---|---|---|
| `st_platform.infer` | statistical tests / effect sizes / CUPED / correction | `cli/stctl.py`, tests |
| `st_platform.inference` | model runners (`ModelRunner` protocol + `MockRunner`) | **tests only today** |

`st_platform.inference` has no production caller: `grep -rn "st_platform.inference" src/`
matches only its own `__init__.py`. It is the seam a real model service plugs into;
until then the CLI duplicates its own prediction functions. Treat that as the
seam to use when wiring a real runner, and note the duplication rather than
copying the CLI's approach.

---

## 2 · Invariants, and the exact place each is enforced

| # | Invariant | Enforced in (file → symbol) | What breaks it |
|---|---|---|---|
| I-1 | **Task immutability + content addressing**: identical inputs replay the same task; snapshots cannot be mutated after construction | `task/models.py` → `Task.snapshot()` (excludes state/lineage/timestamps), `Task.content_hash` (`@computed_field`, derived never stored), `Task._deep_freeze_params` (pydantic validator), `ALLOWED_TRANSITIONS`; `common/freeze.py` → `FrozenDict`; `task/service.py` → `submit()` (replay by hash), `retry()` (mints a new id) | assigning into `task.params` after construction — blocked, not merely discouraged; a hash that is *stored* instead of computed would be able to drift |
| I-2 | **Guardrail before effect**: a fired BLOCK decides the verdict regardless of statistics; the two are never merged into one score | `safety/checker.py` → `SafetyChecker.check` (blocking ids short-circuit the tier; unknown fired id ⇒ BLOCK, recorded in `evidence['_unregistered_fired']`); `report/report.py` → `render_markdown` emits `## Guardrail verdict` before `## Effectiveness` and never computes a combined score | filing a fired-but-unregistered rule under "passing" (this was the shipped defect, see playbook row 7) |
| I-3 | **Correction is mandatory when >1 test is run**, and only corrected p-values may drive a conclusion | `infer/result.py` → `assert_correction_applied`; renderer labels the column `p_corrected (authoritative after correction)` and prints raw and corrected side by side | ⚠️ **partially enforced**: nothing calls `assert_correction_applied` outside `tests/test_result.py`; `PairedResult.p_corrected` is `float | None`, so an uncorrected value renders as the literal `None` in the table. Callers must call the guard — see §5 gap G-1 |
| I-4 | **Append-only store**: an address never changes its bytes; nothing is deleted | `store.py` → `ReportStore.save` raises `StoreConflict` when existing bytes differ; `AuditLedger.verify` walks the hash chain; there is no `delete`/`remove` API for tasks, reports or audit entries (`grep -rn "def delete" src/` → none) | rewriting the file at a content address — refused, and the refusal does not clobber |
| I-5 | **Reproducibility gate**: no report without model version, dataset version + sha, code version, seed | `report/report.py` → `ReproducibilityMeta.validate_complete()`, called by `ReportRenderer.render_markdown` before rendering anything | an empty-string element (blank counts as missing) |
| I-6 | **Determinism**: results must not depend on interpreter hash randomisation | `cli/stctl.py` → `_digest` (sha256 of the case id); `inference/runner.py` → `MockRunner.predict` (seeded from `sha256_hex`); `dataset/core.py` → `Dataset.compute_sha`, `case_signature`; guard: `tests/test_cli_reproducibility.py` runs the CLI as a subprocess under two `PYTHONHASHSEED` values | any use of built-in `hash()` (or an unseeded `random`) in a number that reaches a report |
| I-7 | **Contamination is evidence, not a boolean to be assumed**: the eval/train overlap is computed and travels with the report | `dataset/core.py` → `contamination_detect` + `case_signature`; carried via `ReproducibilityMeta.contamination_result` | passing an empty train signature set: the check then *cannot* fail (the demo does exactly this — see gap G-2) |

---

## 3 · How to add a metric

1. `registry/metrics.py` — define it, do not hardcode a rate anywhere:
   `MetricDefinition(metric_id="m.<name>", name=..., kind=MetricKind.RATE, direction=Direction.HIGHER_BETTER, owner="st-ledger", formula=...)`.
   `MetricRegistry.register` assigns `version = len(history) + 1` and raises
   `RegistryError` if you hand it a non-incremental `version`; each registration
   appends a history row (`all_versions`), so a definition change is a new version, not
   an edit.
2. Measure it in `infer/` (paired comparison against the same case set) so that the
   statistic is produced by a tested function, not inline in a caller.
3. Correct it: build `PairedResult(..., p_raw=..., p_corrected=...)` and call
   `assert_correction_applied(results)` when you have more than one test.
4. Render it: `ReportRenderer.render_markdown(results=[...])` already prints
   name / `p_raw` / `p_corrected` from any object with those attributes — no
   renderer change needed. Add a `## ` section only if the metric needs a table the
   renderer cannot infer.
5. Test it with a known-answer fixture plus one degenerate input (`n=1`,
   all-identical values) — the codebase's convention is that degenerate inputs
   raise or return an explicitly tagged value, never `NaN`.

## 4 · How to add a redline

1. `safety/rules.py` — instantiate `DiagnosticRedline(id="rl.<stable_id>", severity_level="BLOCK"|"WARN", description=...)`
   (or `ComplianceRedline`, which defaults to `BLOCK`). Ids are the key:
   `RedlineSet.add` de-duplicates by `id`, keeping the first position.
2. Register it in the set you hand to `SafetyChecker([...])`. **A rule that is not
   in the set is not a rule**: a fired unknown id is fail-closed to `BLOCK` and
   listed in `verdict.evidence['_unregistered_fired']`.
3. Supply a result for it: `checker.check(results_by_rule={"rl.<id>": <bool|value>})`.
   A truthy value means the rule **fired** (violation).
4. Coverage: `CoverageReport(registered=..., evaluated=...)` computes
   `covered/uncovered` counts; `recall(known_risks)` is over the *known-risk set
   your compliance owner supplied* — it is not a claim of "zero misses".
   Keep `registered` and `evaluated` ids honest; `to_dict()` prints both sets.
5. Update `docs/self-review-playbook.md` when a redline defect is found, and keep
   the redline set's content decision with medical/compliance (`design.md` §9 Q5).

---

## 5 · Known drift and open gaps (verified, not fixed here)

| # | Gap | Evidence | Consequence |
|---|---|---|---|
| G-1 | Correction is opt-in | `grep -rn assert_correction_applied src/` → only the definition in `infer/result.py` and the re-export in `infer/__init__.py`; no production caller | a caller can emit uncorrected p-values; the report prints the literal `None` in the `p_corrected` column |
| G-2 | The demo's contamination check cannot fail | `cli/stctl.py` → `contamination_detect(ds, set())` | the demo's `contaminated=False` is a property of the empty train set, not of the data |
| G-3 | `contamination_result` is not a required reproducibility element | `ReproducibilityMeta.validate_complete` requires `model_version, dataset_version, dataset_sha, code_version, seed`; `design.md` §4.1 lists the contamination conclusion among its five | a report can pass the gate with `contamination_result: n/a` |
| G-4 | `st_platform.inference` has no production caller | `grep -rn "st_platform.inference" src/` → only its own `__init__.py` | two prediction paths (CLI vs runner); pick the runner when wiring a real model |
| G-5 | `docs/design_go_python.md` describes a target topology (st-control, Prefect, ClickHouse, Kafka) and some P0-era interfaces that do not exist | §5 step 8 says `stctl reports list`; `build_parser` registers `demo` and `reports` (the nested `list` form named in that doc is not implemented). §8 says "Retries = max 1"; `TaskService.retry` has no attempt ceiling. §4 item 5 says task ids look like `T-YYYYMMDD-HHMMSS-rand4`; the code uses `t_<content_hash[:12]>` (+`#r<n>` on retry) | read those sections as the P1 target, not as current behaviour |
| G-6 | The demo CLI exercises a **subset** of the invariants: `cmd_demo` builds registry → dataset → infer → safety → report → audit, but never creates a `Task` and never calls `ReportStore` | `grep -n "TaskService\|ReportStore" src/st_platform/cli/stctl.py` → no match | task immutability/retry and the append-only store are enforced and tested but not yet on any end-to-end path; wiring them is P1 work (`RUNBOOK.md` §2.2 shows the manual chain) |

## 6 · Where to add tests

One file per concern, mirroring the package (`tests/test_store.py`,
`tests/test_task.py`, `tests/test_effect.py`, ...). The conventions worth copying:

- real code paths only — no monkeypatching of the class under test;
- a regression test names the defect it prevents (see `tests/test_cli_reproducibility.py`
  and `tests/test_effect.py::test_naive_ci_would_declare_significance_the_honest_ci_cannot`);
- subprocess tests when the property is process-level (hash randomisation), because
  an in-process test cannot observe it (`AGENTS.md` D-11).

```bash
PYTHONPATH=src /usr/local/bin/python3 -m pytest -v tests/    # 114 passed
```
