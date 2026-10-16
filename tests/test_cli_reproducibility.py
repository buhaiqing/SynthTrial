"""CLI output must not depend on interpreter hash randomization.

Regression guard: the demo used Python's built-in hash(), which is salted per
process (PYTHONHASHSEED). Identical input then produced different accuracy
numbers on every run -- a direct violation of the report-credibility rule
(docs/design.md 4.1). Run the CLI as a subprocess under two different
PYTHONHASHSEED values; an in-process test cannot observe this at all.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _run_demo(hashseed: str) -> dict:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hashseed
    env["PYTHONPATH"] = "src"
    proc = subprocess.run(
        [sys.executable, "-m", "st_platform.cli.stctl", "demo", "--n", "40", "--json"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def _accuracy_line(report: str) -> str:
    return next(ln for ln in report.splitlines() if "Accuracy before" in ln)


# NOTE: do NOT assert only on one derived number. Two hash seeds can
# coincidentally yield the same accuracy (mutation testing showed the
# accuracy-line assertion passing against salted hash()). The full-report
# comparison below is the guard that actually discriminates.
def test_demo_full_report_is_identical_across_hash_seeds():
    a = _run_demo("0")
    b = _run_demo("987654")
    assert a["report"] == b["report"], "full report text differed across hash seeds"


def test_demo_contamination_check_is_not_vacuous():
    """T-M7-06: the demo must actually exercise contamination detection.

    With an empty train-signature set the check is structurally incapable of
    firing, so a BLOCK-capable demo proved nothing. Guardrail-before-effect
    (AGENTS.md 3.3) means showing the guardrail trip is the demo's job.
    """
    payload = _run_demo("0")
    out = payload["report"]
    # \b, not a plain substring: "train_overlap_count=3" is a prefix of
    # "train_overlap_count=37", so an `in` check passes on the wrong count.
    # Mutation-verified (playbook row 4 / D-11): widening the demo's signature
    # set from rows[:3] to rows[3:] must fail here.
    assert re.search(r"train_overlap_count=3\b", out), f"contamination check is vacuous:\n{out}"
    assert re.search(r"contaminated=True\b", out), f"demo must demonstrate the BLOCK path:\n{out}"
    assert payload["verdict"] == "BLOCK", "contaminated demo data must not report PASS"


def test_candidate_is_not_worse_than_baseline():
    """The demo must exercise the paired test with an actual improvement."""
    out = _run_demo("0")["report"]
    before = float(next(ln for ln in out.splitlines() if "Accuracy before" in ln).split(":")[1])
    after = float(next(ln for ln in out.splitlines() if "Accuracy after" in ln).split(":")[1])
    assert after > before, f"demo shows a regression ({before} -> {after}), not a lift"
