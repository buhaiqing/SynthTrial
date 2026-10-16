# SynthTrial M9 · T-M9-06 Plan

## Slice 1 — Core model + assignment
DoD: `layers.py` with `Experiment`, `Layer`, `assign`; tests pass.
Verify: `PYTHONPATH=src pytest -q tests/test_layers.py`.

## Slice 2 — Package export + consistency
DoD: export from `bucket` package; deterministic across processes.
Verify: `python3 tools/verify_bucket_consistency.py --samples 1000` (existing) + new layer determinism check.