"""`ariadne compare` nets a candidate's effect vs a baseline; verdict drives the exit code."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ariadne.cli import _run_compare, parse_args

if TYPE_CHECKING:
    from pathlib import Path

_CLEAN = {
    "fixture": "halberd",
    "grounded": True,
    "recall": 1.0,
    "trajectory": 1.0,
    "supporting_fact_f1": 1.0,
    "citation_coverage": 1.0,
}
_DEGRADED = {**_CLEAN, "grounded": False, "citation_coverage": 0.8}


def _write_run(tmp_path: Path, name: str, scores: dict) -> Path:
    run_dir = tmp_path / name
    run_dir.mkdir()
    (run_dir / "eval.json").write_text(json.dumps(scores), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({"model": "claude-opus-4-8", "profile": "default", "params": {}}),
        encoding="utf-8",
    )
    return run_dir


def test_compare_flags_parse() -> None:
    a = parse_args(["compare", "--baseline", "b1", "b2", "--candidate", "c1"])
    assert a.baseline == ["b1", "b2"]
    assert a.candidate == ["c1"]
    assert a.out is None
    assert (
        parse_args(["compare", "--baseline", "b", "--candidate", "c", "--out", "x.json"]).out
        == "x.json"
    )


def test_run_compare_ratify_exits_zero(tmp_path, capsys) -> None:
    base = _write_run(tmp_path, "base", _DEGRADED)
    cand = _write_run(tmp_path, "cand", _CLEAN)
    rc = _run_compare([str(base)], [str(cand)])
    assert rc == 0
    assert "ratify" in capsys.readouterr().out.lower()


def test_run_compare_reject_exits_one(tmp_path, capsys) -> None:
    base = _write_run(tmp_path, "base", _CLEAN)
    cand = _write_run(tmp_path, "cand", _DEGRADED)
    rc = _run_compare([str(base)], [str(cand)])
    assert rc == 1
    assert "reject" in capsys.readouterr().out.lower()


def test_run_compare_incomparable_exits_two(tmp_path, capsys) -> None:
    base = _write_run(tmp_path, "base", _CLEAN)
    cand = _write_run(tmp_path, "cand", {**_CLEAN, "fixture": "wren-tie"})
    rc = _run_compare([str(base)], [str(cand)])
    assert rc == 2
    assert "compare" in capsys.readouterr().err.lower()


def test_run_compare_writes_out(tmp_path) -> None:
    base = _write_run(tmp_path, "base", _DEGRADED)
    cand = _write_run(tmp_path, "cand", _CLEAN)
    out = tmp_path / "comparison.json"
    rc = _run_compare([str(base)], [str(cand)], out=str(out))
    assert rc == 0
    assert json.loads(out.read_text(encoding="utf-8"))["verdict"] == "ratify"
