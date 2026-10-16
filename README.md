# SynthTrial (st-platform v2.0)

Medical model offline evaluation P0 core: metric registry, immutable task lifecycle, paired statistical engine (with CUPED + Bonferroni/Holm/BH), fail-closed safety redlines, hidden-state coverage accountability, decision-ready report + hash-linked audit ledger.

Technology stack: Python-first monolith for P0/P1, Go control plane (`st-bucket` / `st-ledger`) only at tails. Authoritative requirements and architecture are in `docs/design.md` + `docs/design_go_python.md`.

## 1. Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make test            # run all tests
```

One-command demo (no external infra):

```bash
make run            # PYTHONPATH=src python3 -m st_platform.cli.stctl demo
# or
PYTHONPATH=src python3 -m st_platform.cli.stctl demo --n 200 --json
```

Expected: markdown evaluation report with reproducibility block (model version / dataset version + sha / code version / seed / contamination), paired p-values (p_raw + p_corrected side by side), and guardrail verdict (BLOCK / WARN / PASS).

## 2. Project layout

```
src/st_platform/
├── common/      # types, hashes, SafetyVerdictTier
├── registry/    # metric registry (versioned, append-only)
├── audit/       # hash-linked append-only audit ledger
├── dataset/     # immutable dataset + contamination detection
├── task/        # content-addressed task + explicit state machine
├── inference/   # deterministic model runner protocol + MockRunner
├── infer/       # paired t / Wilcoxon / McNemar, effect + CI, CUPED, multicorrect
├── safety/      # fail-closed redline checker + coverage accountability
├── report/      # reproducibility validation (5 elements) + rendering
└── cli/         # stctl
tests/           # 91 tests across all slices
docs/            # requirements, architecture, superpowers specs/plans
```

## 3. Vertical slices shipped (P0)

1. Domain foundations + registry + audit (12 tests)
2. Task lifecycle + model runner (30 tests)
3. Paired statistical engine (40 tests)
4. Safety redlines + coverage + report (33 tests; patched during merge for 2 hidden defects)
5. CLI + docs + end-to-end validation (Makefile, demo works)

## 4. Key design decisions

- **Immutable batches.** `content_hash` is derived solely from the snapshot (model version / dataset id+version+sha / seed / params); no `task_id`, no timestamps. Re-running identical inputs returns the same task.
- **Explicit lifecycle.** Allowed transitions map (`ALLOWED_TRANSITIONS`); `FAILED -> RUNNING` forbidden; retries mint *new* tasks (`parent_task_id` / `attempt`), never overwrite.
- **Paired test discipline.** `mcnemar` for matched binary, Wilcoxon for continuous non-parametric, paired t for parametric. Aligned-by-`case_id` validation raises rather than silently reordering.
- **CUPED.** Theta = Cov(metric, covariate)/Var(covariate); raise if covariate variance 0 (mathematically undefined, not a style choice).
- **Multiple-comparison correction forced** when metric × subgroup > 1. `p_corrected` reported alongside `p_raw`; renderer marks the corrected as authoritative.
- **Relative lift CI uses the delta method**, propagating baseline-mean sampling variance; the naive absolute-CI / baseline-mean definition understates uncertainty and explodes near baseline 0 (rare adverse-event metrics).
- **Fail-closed safety.** A `BLOCK`-severity verdict cannot be overridden by any downstream success; unregistered rule ids fired are classified as `BLOCK` rather than silently bucketed into `PASS`. Coverage is surfaced as covered/uncovered/ratio so the report never brags about recall it cannot guarantee.
- **Reproducibility as a publish gate.** Reports must carry all 5 elements (model_version, dataset_version, dataset_sha, code_version, seed); `validate_complete()` raises rather than silently rendering an un-auditable report.
- **Anti-over-claim.** `recall()` over a known-risk set returns at most 1.0; no `zero_miss` / `perfect_recall` / `100% safety` symbols. Medical safety SLOs are downgraded to auditable bounds, per AGENTS.md §4.

## 5. Operational conventions (excerpt)

- Subagent model is identical to the main agent (no fallback chain without user sign-off).
- Fast/cheap work: direct execution. Multi-subagent orchestration via `subagent-orchestrator`; `decide.py` first, preflight when batch > 1, disk-first post-dispatch verification (subagent claims are hints, disk is ground truth).
- Discipline `D-1`..`D-9` in AGENTS.md §7.
- Toolchain in AGENTS.md §8.
- Every PR: lint zero error; tests green; `check_outcome_backfill.py` / GCL if structural.

## 6. License

Internal.
