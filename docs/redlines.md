# Redline list & κ threshold (Q4/Q5)

Values are **config-driven**, not hardcoded, so compliance/medical sign-off can
change them without a code release.

- Config file path: `ST_CONFIG_PATH` env var (default `./config/st-platform.json`).
- κ threshold: `ST_KAPPA_THRESHOLD` env var overrides the file value; default
  `0.6` (seed, pending medical sign-off — Q4).
- Redline list: `redlines` array in the config file (each item: `id`,
  `severity`, `description`, `version`). If absent, seed defaults are used and a
  warning is printed (pending compliance sign-off — Q5).

When no config is present, the platform runs in **seed mode** and prints a
warning on every `stctl run`. This is intentional: it makes the "pending
sign-off" status visible at runtime rather than silently passing.
