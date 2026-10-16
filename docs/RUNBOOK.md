# SynthTrial Operator Runbook (st-platform P0)

> Audience: whoever is on the hook when an evaluation misbehaves.
> Requirements live in `docs/design.md`; module rules in `docs/ARCHITECTURE.md`.
> **Every command in this file was executed on this checkout** (Python 3.12.1,
> pytest 7.4.4, 2026-10-17) before it was written down. Numbers quoted below are
> observed output, not expectations.

---

## 0 · What actually exists (do not assume more)

| Surface | State | Evidence |
|---|---|---|
| `stctl demo` | works, prints a report to stdout | `src/st_platform/cli/stctl.py` → `build_parser` registers exactly one subcommand |
| Report **persistence** | library only: `ReportStore`; **the CLI does not persist anything** | `cmd_demo` never constructs a store (`grep -n ReportStore src/st_platform/cli/stctl.py` → no match) |
| Task lifecycle | in-memory `TaskService`; a process exit loses tasks | `src/st_platform/task/service.py` — `TaskService._tasks: dict` |
| `stctl reports list` (design_go_python.md §5 step 8) | **does not exist**; use the `ReportStore` listing below | `PYTHONPATH=src /usr/local/bin/python3 -m st_platform.cli.stctl --help` → `usage: stctl [-h] {demo} ...` |
| Task lifecycle in the CLI | not wired: `stctl demo` never creates a `Task` | `grep -n "TaskService" src/st_platform/cli/stctl.py` → no match; drive tasks via the library (`ARCHITECTURE.md` G-6) |
| HTTP API, Prefect, Kafka, ClickHouse, Postgres | not implemented in P0 | no such modules under `src/st_platform/` |

---

## 1 · Prerequisites and install

| Requirement | Verified value on the reference machine |
|---|---|
| Python | 3.12.1 at `/usr/local/bin/python3` (`pyproject.toml` requires `>=3.12`) |
| Deps | `requirements.txt`: statsmodels, numpy, scipy, pandas, pydantic, fastapi, pytest, pytest-cov, ruff |
| pytest | 7.4.4 in the pre-installed interpreter; `requirements.txt` asks for `>=8`, and a fresh venv resolved to **9.1.1** — the suite is verified green on both (see below) |

A fresh venv is verified end to end: `python3 -m venv`, `pip install -r requirements.txt`,
`make test` → **114 passed** (that run pulled pytest 9.1.1 / numpy 2.5.4 / pandas 3.0.6 /
scipy 1.18.1 / statsmodels 0.15.0 / pydantic 2.14.1). The pre-installed environment is
older (pytest 7.4.4, numpy 1.26.4) and also green.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

There is no `python` binary on this machine; `python3` is `/usr/local/bin/python3`.

⚠️ `make test` keeps using `/usr/local/bin/python3` even with the venv activated —
`Makefile` sets `PYTHON ?= /usr/local/bin/python3` and activation does not export
`PYTHON`. Verified within the venv: `make -n test` →
`PYTHONPATH=src /usr/local/bin/python3 -m pytest -v tests/`. Pass the interpreter
explicitly to test the venv (`make test PYTHON=python` → 114 passed on pytest 9.1.1),
or call `python -m pytest -v tests/` directly.

### The two commands this repo is verified against

```bash
PYTHONPATH=src /usr/local/bin/python3 -m pytest -v tests/         # -> 114 passed
PYTHONPATH=src /usr/local/bin/python3 -m st_platform.cli.stctl demo
```

`make test` and `make run` are thin wrappers around the same two commands
(`Makefile` sets `PYTHON ?= /usr/local/bin/python3`); both were run and are green.

Note: pytest does **not** need `PYTHONPATH` — `pyproject.toml` sets
`pythonpath = ["src"]` under `[tool.pytest.ini_options]` (verified: bare
`/usr/local/bin/python3 -m pytest tests/ -q` → 114 passed). The CLI *does* need
it; without it you get `ModuleNotFoundError: No module named 'st_platform'`.

---

## 2 · Worked example: produce → persist → retrieve a report

### 2.1 Produce

`stctl demo` renders a full report (guardrail verdict, effectiveness, corrected
p-values, reproducibility block) but keeps it in memory:

```bash
PYTHONPATH=src /usr/local/bin/python3 -m st_platform.cli.stctl demo --n 200 --json
```

`--n` is the synthetic dataset size (default 40); `--json` wraps the markdown in
`{"verdict": ..., "report": ...}`. Exit code 0 = the render path ran; it is **not**
a promotion decision.

### 2.2 Persist and retrieve (the full chain, verified end-to-end)

```bash
cd <repo>            # the store root below is relative to the working directory
PYTHONPATH=src /usr/local/bin/python3 - <<'PY'
from st_platform.dataset.core import Dataset, DatasetSplit, contamination_detect
from st_platform.infer.multicorrect import bonferroni
from st_platform.infer.paired import mcnemar, paired_t_test
from st_platform.infer.result import PairedResult
from st_platform.registry.metrics import MetricDefinition, MetricKind, MetricRegistry
from st_platform.report.report import ReportRenderer, ReproducibilityMeta
from st_platform.safety.checker import SafetyChecker
from st_platform.safety.rules import DiagnosticRedline
from st_platform.store import ReportStore

# 1. metric registry: define the metric once, reference it by id afterwards
reg = MetricRegistry()
reg.register(MetricDefinition(metric_id="m.acc", name="accuracy", kind=MetricKind.RATE, owner="st-ledger"))

# 2. the dataset, plus the contamination conclusion that must ride with it
ds = Dataset(dataset_id="cards-demo", version=1, source="synthetic", split=DatasetSplit.EVAL,
             rows=[{"case_id": f"C{i:03d}", "text": f"s{i}", "label": i % 2} for i in range(40)])
contamination = contamination_detect(ds, set())

# 3. paired evaluation: the SAME cases through baseline and candidate
labels = [r["label"] for r in ds.rows]
before = [1 - l if i % 7 == 0 else l for i, l in enumerate(labels)]
after = list(labels)
t = paired_t_test([float(a == b) for a, b in zip(before, labels)],
                  [float(a == b) for a, b in zip(after, labels)])
mc = mcnemar(before, after)
adj = bonferroni([t["p_value"], mc["p_value"]])           # correction is mandatory when >1 test
results = [
    PairedResult(test_name="accuracy", n=len(labels), statistic=t["statistic"], p_raw=t["p_value"],
                 p_corrected=adj[0], method="paired_t_test", ci_low=t["ci_low"], ci_high=t["ci_high"],
                 abs_lift=0.0, rel_lift=0.0, correction_applied="bonferroni"),
    PairedResult(test_name="mcnemar", n=len(labels), statistic=mc["statistic"], p_raw=mc["p_value"],
                 p_corrected=adj[1], method="mcnemar", ci_low=0.0, ci_high=1.0,
                 abs_lift=0.0, rel_lift=0.0, correction_applied="bonferroni"),
]

# 4. guardrail verdict, computed independently of the effect numbers
checker = SafetyChecker([DiagnosticRedline(id="rl.no_missed_critical", severity_level="BLOCK")])
verdict = checker.check(results_by_rule={"rl.no_missed_critical": contamination["contaminated"]})

# 5. reproducibility metadata -- the renderer refuses a report without all five
repro = ReproducibilityMeta(model_version="model-v2.0.0",
                            dataset_version=f"{ds.dataset_id}@{ds.version}",
                            dataset_sha=ds.compute_sha(), code_version="st-platform@0.1.0",
                            seed=42, contamination_result=contamination)
repro.validate_complete()
md = ReportRenderer().render_markdown(repro=repro, results=results, verdict=verdict,
                                      accuracy_before=0.9, accuracy_after=1.0)

# 6. persist (content-addressed) then retrieve by content id
store = ReportStore(".runtime/reports")
content_id = store.save({"task_id": "t_demo00000000", "report_markdown": md,
                         "verdict": verdict.tier.value,
                         "repro": {"model_version": repro.model_version,
                                   "dataset_version": repro.dataset_version,
                                   "dataset_sha": repro.dataset_sha,
                                   "code_version": repro.code_version, "seed": repro.seed}})
print("content_id:", content_id)
print("retrievable:", store.get(content_id)["verdict"])
PY
```

Observed on the reference machine:

```text
content_id: 0b3276815c8a580e152ba7020888bedc44c3e6a1eca7286e9a48cde48ebaf62c
retrievable: PASS
```

### 2.3 Where it is persisted (the real layout)

`src/st_platform/store.py`:

- path: `<root>/<content_id>.json` — flat, one file per report, no sharding, no index;
- `content_id = sha256(json.dumps(payload, sort_keys=True, default=str))`.
  It hashes the **canonical payload**, not the file bytes; key order does not
  change the id, and `default=str` coerces anything non-JSON (datetime, Decimal)
  into its `str()` form before hashing;
- writes go to `tempfile.mkstemp(dir=<root>)` then `os.replace`; temp and target
  sit in the same directory, so a crash can never leave a half-written file that
  would later read as a valid report. That relies on the root's filesystem
  providing atomic rename — keep the root local rather than on a network mount.
  Files land with `mkstemp`'s `0600` permissions (verified with `ls -la`), so
  another unix user cannot read them as-is;
- append-only: re-saving the same payload is idempotent (same id, no rewrite);
  re-saving an id whose bytes on disk differ raises `StoreConflict` and leaves
  the on-disk file untouched;
- `summaries()` returns `task_id / model_version / baseline_model_version /
  verdict / created_at` when present, and marks unreadable files
  `{"hash": ..., "corrupt": True}` instead of skipping them.

### 2.4 Retrieve

```bash
PYTHONPATH=src /usr/local/bin/python3 -c "
from st_platform.store import ReportStore
s = ReportStore('.runtime/reports')
for row in s.summaries(): print(row)
h = s.list_hashes()[0]
print(s.get(h)['report_markdown'].splitlines()[0])
"
```

Observed:

```text
{'hash': '0b3276815c8a580e152ba7020888bedc44c3e6a1eca7286e9a48cde48ebaf62c', 'task_id': 't_demo00000000', 'verdict': 'PASS'}
# Evaluation Report
```

`.runtime/` is gitignored, so a store rooted there never dirties the checkout.

---

## 3 · Incident procedures

### 3.1 (a) A redline BLOCKed a model

`verdict.tier` is `BLOCK`, and `verdict.blocking_ids` names the rules that fired.
Read them in this order:

| Step | Do |
|---|---|
| 1 | `verdict.blocking_ids` → the rule ids. `verdict.evidence` holds each rule's raw result. |
| 2 | Check `verdict.evidence['_unregistered_fired']`. Non-empty means a rule id fired that is **not registered** — `SafetyChecker.check` classifies it as BLOCK on purpose (fail-closed) and records it there. Usually a typo or a rule that was never added to the set. Fix the rule set, do not relax the checker. |
| 3 | Check `verdict.uncovered_rule_count` / `uncovered_ratio`. Non-zero = registered rules that were never evaluated; the report is not evidence of coverage for them. |
| 4 | Escalate. Per `docs/design.md` §9 Q5 the redline set and its update mechanism are owned by medical/compliance — **the operator cannot clear a BLOCK, and neither can the engineer who ran it**. Approval is out-of-band; nothing in this codebase records an approval token yet. |
| 5 | Do not retry hoping for a different verdict. The verdict is a pure function of the inputs; a different verdict means different inputs, which is a new evaluation, not a retry. |

The block cannot be overridden from the outside either: `blocking_ids` short-circuits
the tier computation ahead of the warning/pass path (`SafetyChecker.check`), and
`tests/test_safety.py::test_checker_block_cannot_be_overridden` pins that.

### 3.2 (b) A task FAILED — how to retry, and why the id changes

Verbatim output of a probe against `TaskService` on this checkout:

```text
identical: True
retry RUNNING -> TaskStateError : cannot retry task in state RUNNING; retryable: DONE, FAILED, OBSOLETED, SUBMITTED
retry FAILED -> new id: t_f058992f5866#r1 | attempt: 1 | parent state: FAILED
```

(The ids are content-derived, so they repeat exactly for this fixture; the parent's
state is still `FAILED` after the retry — the parent row was not touched.)

Reproduce it:

```bash
cd <repo>
PYTHONPATH=src /usr/local/bin/python3 - <<'PY'
from st_platform.dataset.core import Dataset, DatasetSplit
from st_platform.task.models import TaskState, TaskStateError
from st_platform.task.service import TaskService

ds = Dataset(dataset_id="cards-demo", version=1, source="synthetic", split=DatasetSplit.EVAL,
             rows=[{"case_id": "C1"}])
svc = TaskService()
t1 = svc.submit(model_version="m-v2", dataset=ds, seed=42)
t2 = svc.submit(model_version="m-v2", dataset=ds, seed=42)
print("identical:", t1.task_id == t2.task_id)
svc.transition(t1.task_id, TaskState.RUNNING)
try:
    svc.retry(t1.task_id)
except TaskStateError as e:
    print("retry RUNNING ->", type(e).__name__, ":", e)
svc.transition(t1.task_id, TaskState.FAILED)
r = svc.retry(t1.task_id)
print("retry FAILED -> new id:", r.task_id, "| attempt:", r.attempt,
      "| parent state:", svc.get(t1.task_id).state.value)
PY
```

Rules, from `src/st_platform/task/service.py` + `task/models.py`:

- `retry` is legal only from `SUBMITTED`, `DONE`, `FAILED`, `OBSOLETED`
  (`RETRYABLE_PARENT_STATES`). Retrying a `RUNNING` or `DRAFT` task raises
  `TaskStateError`;
- the retry is minted as a **new row** `"<parent_id>#r<attempt>"` with
  `attempt = parent.attempt + 1` and `parent_task_id` set. The parent object is
  never mutated, never overwritten, never deleted;
- **why a new id instead of reusing the old one:** identity is
  `content_hash = sha256(canonical snapshot)`, and `TaskService.submit` returns
  the *same* task for the *same* snapshot. The snapshot deliberately excludes
  state, timestamps and lineage. So if a retry reused the parent id, a second
  run of identical inputs would collide with — and silently overwrite — the
  record of the first run, destroying exactly the audit trail (`AGENTS.md` D-3,
  `docs/design.md` §3 M006 F1) that says what was run and what came out. The
  new id is what makes "two attempts at the same snapshot" representable. The
  `FAILED -> RUNNING` edge is absent from `ALLOWED_TRANSITIONS` for the same
  reason; `tests/test_task.py::test_failed_task_cannot_be_restarted_in_place`
  pins it.
- `TaskService` is in-memory: after a process restart both the failed task and
  its retry are gone. Persisting the task table is P1 work, not a runbook step.

### 3.3 (c) A report's numbers are questioned — reproduce it

Reproduction means: same code, same inputs, same seed → same numbers. The report
must carry all of that; `ReproducibilityMeta.to_block()` renders them.

| # | Element | Where it comes from | How the operator re-establishes it |
|---|---|---|---|
| 1 | `model_version` | the candidate under test | check out / point at that model version again |
| 2 | `dataset_version` | `Dataset.dataset_id` + `version` | use the same dataset version |
| 3 | `dataset_sha` | `Dataset.compute_sha()` = sha256 of `json.dumps(rows, sort_keys=True, default=str)` | rebuild the dataset and compare this line **first** — if it differs, nothing else can match |
| 4 | `code_version` | the running build (`st-platform@0.1.0`) | `git rev-parse HEAD` on the evaluation machine; compare with the commit the report names |
| 5 | `seed` | RNG seed (`42` in the demo) | re-run with the same seed |
| 6 | `contamination_result` | `contamination_detect(eval_dataset, train_signatures)` | re-run the contamination check with the same train signature set |

Elements 1–5 are enforced (see the drift note below); element 6 is rendered but
**not** enforced — see §3.4.

Worked reproduction of the demo's own report:

```bash
cd <repo>
PYTHONPATH=src /usr/local/bin/python3 -m st_platform.cli.stctl demo --n 40 | grep -E "dataset_sha|Accuracy"
PYTHONPATH=src /usr/local/bin/python3 -m st_platform.cli.stctl demo --n 40 | grep -E "dataset_sha|Accuracy"
```

```text
- Accuracy before: 0.825
- Accuracy after: 0.9
- dataset_sha: e9a5ab05174783d6d7763c97256634a40b2d88fe4e1fec4198c584dbad8fb821
--run1 / --run2 identical
```

Also confirm the run is insensitive to interpreter hash randomisation (a defect
that was actually shipped once — see `docs/self-review-playbook.md` row 3):

```bash
PYTHONHASHSEED=1    PYTHONPATH=src /usr/local/bin/python3 -m st_platform.cli.stctl demo --n 200 > /tmp/a.md
PYTHONHASHSEED=99991 PYTHONPATH=src /usr/local/bin/python3 -m st_platform.cli.stctl demo --n 200 > /tmp/b.md
diff /tmp/a.md /tmp/b.md && echo IDENTICAL
```

Observed: `IDENTICAL` (no diff output).

If the numbers still disagree with the report, stop and treat it as a defect:
file the two artifacts (report text + `dataset_sha` + `git rev-parse HEAD`) rather
than re-running until it looks right.

### 3.4 Known drift, operator-relevant

`docs/design.md` §4.1 lists five reproducibility elements and counts the
**contamination conclusion** among them. The implementation requires a different
set — `ReproducibilityMeta.validate_complete` demands `model_version`,
`dataset_version`, `dataset_sha`, `code_version`, `seed` and does **not** require
`contamination_result` (it renders `n/a` when absent). So a report that passes
`validate_complete()` can lack the contamination conclusion. Treat a report with
`contamination_result: n/a` as **unfit for a promotion decision** until the
contamination check is re-run into it. Fixing the code is a P1 item; this runbook
records the gap rather than papering over it.

---

## 4 · Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `ModuleNotFoundError: No module named 'st_platform'` | CLI run without `PYTHONPATH=src` (verified: bare run fails) | prefix the command with `PYTHONPATH=src`, or run `make run` |
| `python: command not found` | no `python` binary on this machine | use `/usr/local/bin/python3` |
| `KeyError: '<hash>'` from `store.get` | content id not in this store root, or wrong root/CWD | `store.list_hashes()` / `summaries()`; the root is relative to the working directory |
| `StoreConflict: ... already holds different content; refusing to overwrite (append-only)` | the on-disk file was edited, or two writers computed the same id with different bytes | **do not delete the file.** Copy the store root aside, diff the payload you are saving against `get(hash)`, and report the tampering |
| `{"hash": ..., "corrupt": true}` in `summaries()` | unreadable/truncated JSON at that address | same as above: quarantine a copy, never delete in place |
| store file present but empty/truncated after a power loss | root on a filesystem whose rename is not atomic/durable (e.g. some network mounts) | move the root to a local filesystem; temp+rename in the same directory only protects you where rename is atomic |
| `TaskStateError: illegal transition X -> Y` | wrong order in the lifecycle | see `ALLOWED_TRANSITIONS` in `task/models.py`; terminal `OBSOLETED` has no outgoing edges |
| `TaskStateError: cannot retry task in state RUNNING` | retry attempted while in flight | wait for `FAILED`/`DONE`, then retry (a retry mints a new id) |
| `TaskNotFound: unknown task_id ...` | `TaskService` is in-memory and the process restarted | re-submit the snapshot; identical inputs reproduce the same content hash/id |
| `ReportError: missing required reproducibility elements: [...]` | an element is empty/blank/zero-length | fill it in; the renderer refuses partial meta on purpose |
| `ValueError: paired t-test needs at least 2 pairs` / `undefined: every difference is the same non-zero value` | degenerate sample | no statistic exists; get more pairs or drop the test. NaN is never returned (it would read as "no effect") |
| `ValueError: before and after are not aligned by case_id` | the two model runs saw different case sets/orders | re-run both arms over the same dataset slice; never reorder one side |
| `ValueError: relative_lift_ci undefined when before_mean == 0` | baseline rate is zero | report absolute lift only |
| verdict `BLOCK` with `_unregistered_fired` non-empty | fired rule id is not in `RedlineSet` | register the rule (or fix the typo); the checker is fail-closed by design |
| report shows `Uncovered: N` with `Uncovered ratio: >0` / `Recall (known risks): 1.0` | rules registered but never evaluated | recall is over the **known-risk set only**; uncovered rules are not covered evidence — read both numbers together |
| `## Annotation quality (low κ)` block appears | a subset's κ is below `0.6` (`DEFAULT_KAPPA_THRESHOLD`) or missing | the report labels those subsets `结论仅供参考` — advisory only; do not promote on them |
| numbers differ between two runs of the same report | different `dataset_sha` / `code_version` / seed, or hash-randomisation dependence | run the §3.3 reproduction steps before believing either number |

---

## 5 · Do NOT

| Do not | Why |
|---|---|
| Delete, truncate, or "clean up" anything under a store root | The store is append-only evidence (`AGENTS.md` D-5, zero-delete). `StoreConflict` is the guard; deleting the file destroys the audit trail that the report depends on. Quarantine a **copy**. |
| Overwrite an existing content-id file to "fix" a report | Same id must mean the same bytes; the store refuses, and so should you. A corrected report is a new payload with a new id. |
| Retry a finished task "in place" | `FAILED -> RUNNING` is not a legal transition; re-running mints `<id>#r<n>`. Editing the old row is the defect, not the fix. |
| Re-run a BLOCKed evaluation until the verdict changes | The verdict is a pure function of inputs. Changing inputs changes the question, not the answer. BLOCK clearance is a medical/compliance decision (`design.md` Q5). |
| Mutate `task.params` (or any snapshot field) after submission | Snapshots are deep-frozen (`common/freeze.py::FrozenDict`); a mutated snapshot would move `content_hash` away from the results it addresses (see playbook row 5). |
| Put patient data into logs, report text, or the store without the redaction path (`AGENTS.md` D-4) | P0 has no redaction layer yet; anything you persist stays. |
| Use `hash()` when deriving any identifier, seed, or ordering from data | Salted per process (`PYTHONHASHSEED`) — use `sha256_hex` (`common/types.py`); this exact defect shipped once (playbook row 3). |
| Assume write-then-rename protects a store root on a network mount | The guarantee holds only where `rename` is atomic; keep the root local. |
| Treat `stctl demo`'s exit code as a promotion decision | Demo output is synthetic; only the runbook §3.3 chain plus the guardrail verdict speaks to a real model. |
