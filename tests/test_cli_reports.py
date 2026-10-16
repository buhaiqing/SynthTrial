"""stctl reports — listing persisted reports (Slice 5 remainder).

Depends only on ReportStore, which is already merged, so this is buildable now.
"""

from __future__ import annotations

import argparse
import json

from st_platform.cli.stctl import build_parser, cmd_reports
from st_platform.store import ReportStore


def _seed(tmp_path):
    store = ReportStore(tmp_path)
    store.save(
        {
            "task_id": "t_aaa",
            "model_version": "m2",
            "baseline_model_version": "m1",
            "verdict": "PASS",
            "created_at": "2026-01-02",
            "report": "# Report A",
        }
    )
    store.save(
        {
            "task_id": "t_bbb",
            "model_version": "m3",
            "baseline_model_version": "m1",
            "verdict": "BLOCK",
            "created_at": "2026-01-01",
            "report": "# Report B",
        }
    )
    return store


def test_reports_lists_stored_reports(tmp_path, capsys):
    _seed(tmp_path)
    rc = cmd_reports(argparse.Namespace(store=str(tmp_path), json=False))
    out = capsys.readouterr().out
    assert rc == 0
    assert "t_aaa" in out
    assert "t_bbb" in out
    assert "BLOCK" in out


def test_reports_json_is_parseable_and_complete(tmp_path, capsys):
    _seed(tmp_path)
    rc = cmd_reports(argparse.Namespace(store=str(tmp_path), json=True))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert len(payload) == 2
    verdicts = {row["verdict"] for row in payload}
    assert verdicts == {"PASS", "BLOCK"}
    # every entry carries its content hash so it can be fetched later
    assert all(len(row["hash"]) == 64 for row in payload)


def test_reports_on_empty_store_is_not_an_error(tmp_path, capsys):
    rc = cmd_reports(argparse.Namespace(store=str(tmp_path), json=False))
    out = capsys.readouterr().out
    assert rc == 0
    assert "no reports" in out.lower()


def test_reports_on_missing_dir_does_not_crash(tmp_path, capsys):
    missing = tmp_path / "nope"
    rc = cmd_reports(argparse.Namespace(store=str(missing), json=False))
    assert rc == 0
    assert "no reports" in capsys.readouterr().out.lower()


def test_reports_flags_corrupt_entry_rather_than_hiding_it(tmp_path, capsys):
    _seed(tmp_path)
    bad = tmp_path / "deadbeef.json"
    bad.write_text("{ not json")
    rc = cmd_reports(argparse.Namespace(store=str(tmp_path), json=True))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert len(payload) == 3, "corrupt entry must be surfaced, not skipped"
    assert any(row.get("corrupt") for row in payload)


def test_parser_exposes_reports_subcommand():
    ns = build_parser().parse_args(["reports", "--store", "/tmp/x"])
    assert ns.cmd == "reports"
    assert ns.store == "/tmp/x"
