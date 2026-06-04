"""CLI surface for `ariadne eval --reconcile`."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ariadne.cli import _run_eval, parse_args

if TYPE_CHECKING:
    from pathlib import Path


def test_eval_reconcile_defaults_off() -> None:
    assert parse_args(["eval", "./x"]).reconcile is None


def test_eval_accepts_a_reconcile_fixture() -> None:
    assert parse_args(["eval", "./x", "--reconcile", "synthetic"]).reconcile == "synthetic"


def _write_workup(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text(
        "Halberd and Wren are both at Compound-Alpha; the personnel records "
        "corroborate this, consistent across both stores. Talon's location conflicts: "
        "the personnel record lists Compound-Beta.",
        encoding="utf-8",
    )
    ledger = [
        {"id": "g1", "tool_input": {"query": "MATCH (u)-[:CO_LOCATED]->(s) RETURN s"}},
        {"id": "g2", "tool_input": {"sql": "SELECT * FROM personnel"}},
    ]
    (tmp_path / "provenance.jsonl").write_text(
        "\n".join(json.dumps(e) for e in ledger), encoding="utf-8"
    )


def test_run_eval_prints_reconciliation_when_requested(tmp_path, capsys) -> None:
    _write_workup(tmp_path)
    _run_eval(str(tmp_path), "halberd", reconcile="synthetic")
    out = capsys.readouterr().out
    assert "reconciliation" in out.lower()


def test_run_eval_omits_reconciliation_by_default(tmp_path, capsys) -> None:
    _write_workup(tmp_path)
    _run_eval(str(tmp_path), "halberd")
    assert "reconciliation" not in capsys.readouterr().out.lower()
