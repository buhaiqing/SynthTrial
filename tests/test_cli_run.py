"""stctl run — wires EvaluationPipeline to the CLI (tasks.md T-M7-01).

These are the tests that close ARCHITECTURE.md G-6: before this, the demo path
exercised a subset of the invariants and the pipeline itself had no caller, so
task immutability, retry and the append-only store were tested but never on an
end-to-end path.

Nothing here mocks the pipeline, the runners or the store: the point of these
tests is that the real vertical slice works.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from st_platform.cli.stctl import build_parser, cmd_reports, cmd_run, cmd_sample
from st_platform.dataset.core import case_signature
from st_platform.store import ReportStore

REPO = Path(__file__).resolve().parents[1]


def _write_dataset(tmp_path: Path, n: int = 30) -> Path:
    """A deterministic synthetic evaluation set (P0 has no data plane yet)."""
    rows = [
        {"case_id": f"C{i:03d}", "text": f"合成病例 {i}", "label": i % 2, "age": 30 + i % 40}
        for i in range(n)
    ]
    path = tmp_path / "eval.json"
    path.write_text(json.dumps({"dataset_id": "cards-test", "rows": rows}, ensure_ascii=False))
    return path


def _args(tmp_path: Path, dataset: Path, **over) -> argparse.Namespace:
    base = {
        "dataset": str(dataset),
        "model_version": "cand-v2",
        "baseline_version": "base-v1",
        "store": str(tmp_path / "store"),
        "seed": 42,
        "n": 30,
        "json": False,
        "out": str(tmp_path / "sample.json"),
        "open_ui": False,
        "train_signatures": None,
    }
    base.update(over)
    return argparse.Namespace(**base)


# ---------------------------------------------------------------- wiring


def test_run_persists_a_report(tmp_path, capsys):
    ds = _write_dataset(tmp_path)
    rc = cmd_run(_args(tmp_path, ds))
    out = capsys.readouterr().out
    assert rc == 0, out
    store = ReportStore(tmp_path / "store")
    assert store.list_hashes(), "run must persist the report"
    assert "# Evaluation Report" in out


def test_run_report_is_listable_by_reports_command(tmp_path, capsys):
    """Closes T-M7-05: run -> reports, the chain the RUNBOOK tells operators to use."""
    ds = _write_dataset(tmp_path)
    cmd_run(_args(tmp_path, ds))
    capsys.readouterr()
    rc = cmd_reports(argparse.Namespace(store=str(tmp_path / "store"), json=False))
    listing = capsys.readouterr().out
    assert rc == 0
    assert "cand-v2" in listing


def test_run_is_deterministic_across_invocations(tmp_path, capsys):
    ds = _write_dataset(tmp_path)
    cmd_run(_args(tmp_path, ds))
    first = capsys.readouterr().out
    cmd_run(_args(tmp_path, ds))
    second = capsys.readouterr().out
    assert first == second, "identical input must produce an identical report"


def test_run_output_carries_reproducibility_five_elements(tmp_path, capsys):
    ds = _write_dataset(tmp_path)
    cmd_run(_args(tmp_path, ds))
    out = capsys.readouterr().out
    for field in ("model_version:", "dataset_version:", "dataset_sha:", "code_version:", "seed:"):
        assert field in out, f"report missing reproducibility element {field}"


def test_run_json_mode_is_parseable(tmp_path, capsys):
    ds = _write_dataset(tmp_path)
    rc = cmd_run(_args(tmp_path, ds, json=True))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert {"task_id", "report_hash", "verdict", "promotable", "report"} <= set(payload)


# ---------------------------------------------------------------- gate


def test_run_exit_code_is_nonzero_when_not_promotable(tmp_path, capsys):
    """Guardrail-before-effect: a non-PASS verdict must not exit 0, so CI can gate on it.

    Forced here by passing a BLOCK redline through the real pipeline rather than by
    stubbing the verdict.
    """
    ds = _write_dataset(tmp_path)
    rc = cmd_run(_args(tmp_path, ds, self_test_block=True))
    out = capsys.readouterr().out
    assert rc != 0, "a BLOCK verdict must not exit 0"
    assert "BLOCK" in out


def test_run_reports_contamination_when_training_overlaps(tmp_path, capsys):
    """The demo could never fail its contamination check (empty train set).
    A real run must be able to."""
    ds = _write_dataset(tmp_path)
    rows = json.loads(ds.read_text())["rows"]

    train_sigs = [case_signature(r) for r in rows[:3]]
    rc = cmd_run(_args(tmp_path, ds, train_signatures=train_sigs, json=True))
    payload = json.loads(capsys.readouterr().out)
    assert payload["contaminated"] is True
    assert payload["contamination_overlap"] == 3
    assert rc != 0, "contaminated eval data must not be promotable"


# ---------------------------------------------------------------- failure path


def test_run_missing_dataset_file_fails_clearly(tmp_path, capsys):
    rc = cmd_run(_args(tmp_path, tmp_path / "nope.json"))
    err = capsys.readouterr().err
    assert rc != 0
    assert "nope.json" in err


def test_run_marks_task_failed_on_a_real_pipeline_error(tmp_path, capsys):
    """T-M7-04: a failure must land the task in FAILED and tell the operator which one.

    The error is real, not stubbed: a duplicated case_id makes the pipeline raise
    UnalignedCases during pairing.
    """
    ds = _write_dataset(tmp_path)
    rows = json.loads(ds.read_text())["rows"]
    rows.append(dict(rows[0]))  # duplicate case_id -> UnalignedCases
    ds.write_text(json.dumps({"dataset_id": "cards-test", "rows": rows}, ensure_ascii=False))

    rc = cmd_run(_args(tmp_path, ds))
    err = capsys.readouterr().err
    assert rc != 0
    assert "FAILED" in err, "operator must be told the task state"
    assert "task_id" in err, "operator must be told WHICH task failed"
    # a failed run must not leave a promotable-looking report behind
    store = ReportStore(tmp_path / "store")
    assert not store.list_hashes(), "a failed run must not persist a report"


def test_run_block_verdict_still_completes_the_task(tmp_path, capsys):
    """A BLOCK verdict is a completed evaluation, not a crash: the task reaches DONE
    and the report is retained for audit. Only the exit code signals 'not promotable'.
    """
    ds = _write_dataset(tmp_path)
    rc = cmd_run(_args(tmp_path, ds, self_test_block=True, json=True))
    payload = json.loads(capsys.readouterr().out)
    assert rc != 0
    assert payload["task_state"] == "DONE"
    assert payload["verdict"] == "BLOCK"
    store = ReportStore(tmp_path / "store")
    stored = store.get(store.list_hashes()[0])
    assert stored["verdict"] == "BLOCK", "a BLOCKed report must still be archived"


# ---------------------------------------------------------------- sample + parser


def test_sample_writes_a_dataset_runnable_by_run(tmp_path, capsys):
    rc = cmd_sample(argparse.Namespace(out=str(tmp_path / "s.json"), n=12))
    assert rc == 0
    payload = json.loads((tmp_path / "s.json").read_text())
    assert len(payload["rows"]) == 12
    assert {"case_id", "label", "text"} <= set(payload["rows"][0])


def test_sample_is_deterministic(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    cmd_sample(argparse.Namespace(out=str(a), n=8))
    cmd_sample(argparse.Namespace(out=str(b), n=8))
    assert a.read_text() == b.read_text()


def test_parser_exposes_run_and_sample():
    p = build_parser()
    r = p.parse_args(["run", "--dataset", "d.json", "--model-version", "v2"])
    assert r.cmd == "run" and r.dataset == "d.json" and r.model_version == "v2"
    s = p.parse_args(["sample", "--n", "5"])
    assert s.cmd == "sample" and s.n == 5


# ---------------------------------------------------------------- script entry point


def _as_script(*argv: str) -> subprocess.CompletedProcess:
    """Invoke stctl as `python -m ...`, not by importing its symbols.

    Importing cmd_run/cmd_sample loads the whole module first, so it cannot catch
    a definition that sits AFTER the `if __name__ == "__main__"` block -- which
    is exactly the bug that shipped 13 green tests alongside a CLI that died with
    NameError. The `python -m` path is the one users actually take.
    """
    env = dict(os.environ, PYTHONPATH="src")
    return subprocess.run(
        [sys.executable, "-m", "st_platform.cli.stctl", *argv],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        # explicit: these tests assert on returncode themselves, including the
        # non-zero paths (a BLOCK verdict must be observable, not raised here).
        check=False,
    )


def test_sample_runs_as_a_script(tmp_path):
    proc = _as_script("sample", "--out", str(tmp_path / "s.json"), "--n", "6")
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "s.json").exists()


def test_run_runs_as_a_script(tmp_path):
    ds = _write_dataset(tmp_path)
    proc = _as_script(
        "run",
        "--dataset",
        str(ds),
        "--model-version",
        "v2",
        "--store",
        str(tmp_path / "store"),
    )
    assert proc.returncode == 0, proc.stderr
    assert "report_hash:" in proc.stdout
    assert "state: DONE" in proc.stdout


def test_every_subcommand_is_reachable_from_the_entry_point():
    """No command may be defined after the __main__ block."""
    proc = _as_script("--help")
    assert proc.returncode == 0, proc.stderr
    for cmd in ("demo", "reports", "run", "sample"):
        assert cmd in proc.stdout, f"{cmd} not reachable from the CLI entry point"
