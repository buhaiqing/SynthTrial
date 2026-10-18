"""Configuration: κ threshold (Q4) and redline list (Q5).

Values are loaded from a JSON config file (path from ``ST_CONFIG_PATH`` env var,
default ``./config/st-platform.json``) and may be overridden by env vars.
Missing config falls back to seed defaults that are explicitly marked as
"pending compliance sign-off" — see docs/redlines.md.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SEED_KAPPA_THRESHOLD = 0.6  # pending medical/compliance sign-off (Q4)
SEED_REDLINES: list[dict[str, Any]] = [
    {
        "id": "rl.contamination",
        "severity": "BLOCK",
        "description": "评测集与训练语料重叠",
        "version": 1,
    },
]


def config_path() -> Path:
    return Path(os.environ.get("ST_CONFIG_PATH", "config/st-platform.json"))


def load_config() -> dict[str, Any]:
    p = config_path()
    if not p.exists():
        return {"kappa_threshold": None, "redlines": None, "_source": "seed"}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"kappa_threshold": None, "redlines": None, "_source": "seed"}
    data["_source"] = str(p)
    return data


def kappa_threshold() -> float:
    env = os.environ.get("ST_KAPPA_THRESHOLD")
    if env is not None:
        try:
            return float(env)
        except ValueError:
            pass
    cfg = load_config()
    v = cfg.get("kappa_threshold")
    if v is not None:
        try:
            return float(v)
        except (TypeError, ValueError):
            pass
    return SEED_KAPPA_THRESHOLD


def redline_list() -> list[dict[str, Any]]:
    cfg = load_config()
    rl = cfg.get("redlines")
    if isinstance(rl, list) and rl:
        return rl
    return [dict(r) for r in SEED_REDLINES]


def is_seed_config() -> bool:
    return load_config().get("_source") == "seed"
