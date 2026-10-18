#!/usr/bin/env python3
"""Cross-process consistency check for st-bucket deterministic bucketing."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

PROGRAM = rf'''
import json, sys
sys.path.insert(0, {str(SRC)!r})
from st_platform.bucket import bucket
samples = json.loads(sys.stdin.read())
out = [bucket(s["user_id"], s["experiment_id"],
              business_line=s["business_line"], salt=s["salt"],
              n_buckets=s["n_buckets"]) for s in samples]
print(json.dumps(out))
'''


def make_samples(n: int) -> list[dict]:
    return [
        {
            "business_line": ["search", "rec", "ads"][i % 3],
            "user_id": f"u{i:06d}",
            "experiment_id": f"exp-{i % 7}",
            "salt": "salt-1",
            "n_buckets": 2 if i % 2 == 0 else 5,
        }
        for i in range(n)
    ]


def run(samples: list[dict], seed: str) -> list[int]:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = seed
    proc = subprocess.run(
        [sys.executable, "-c", PROGRAM],
        input=json.dumps(samples),
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return json.loads(proc.stdout)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=1000)
    args = ap.parse_args()
    samples = make_samples(args.samples)
    a = run(samples, "0")
    b = run(samples, "99991")
    mismatches = [(i, a[i], b[i]) for i in range(len(a)) if a[i] != b[i]]
    if mismatches:
        i, x, y = mismatches[0]
        print(f"INCONSISTENT: {len(mismatches)} mismatches; first at index {i}: {x} vs {y}")
        return 1
    print(f"CONSISTENT: {len(samples)} samples matched across PYTHONHASHSEED 0 and 99991")
    return 0


if __name__ == "__main__":
    sys.exit(main())