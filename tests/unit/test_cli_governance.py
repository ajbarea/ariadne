"""CLI surface for `ariadne governance <workup_dir>` — the offline read-only gate.

Re-audits a persisted run's provenance ledger and gates by default (exit 3 on a
read-only contract breach), the sibling of `eval`/`rubric`. Offline: no API key,
no live stores, runs against a committed workup artifact in CI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ariadne.cli import _run_governance, parse_args
from ariadne.provenance.ledger import ProvenanceLedger

if TYPE_CHECKING:
    from pathlib import Path


def _write_ledger(tmp_path: Path, tool_input: dict[str, str]) -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", tool_input, "rows...")
    led.write_jsonl(tmp_path / "provenance.jsonl")


def test_governance_subcommand_parses() -> None:
    args = parse_args(["governance", "./workups/halberd"])
    assert args.command == "governance"
    assert args.workup_dir == "./workups/halberd"


def test_gate_passes_on_read_only_ledger(tmp_path) -> None:
    _write_ledger(tmp_path, {"query": "MATCH (p:Person) RETURN p"})
    assert _run_governance(str(tmp_path)) == 0


def test_gate_fails_with_exit_three_on_write_attempt(tmp_path, capsys) -> None:
    _write_ledger(tmp_path, {"query": "CREATE (p:Person {name:'X'})"})
    rc = _run_governance(str(tmp_path))
    assert rc == 3
    assert "CREATE" in capsys.readouterr().err


def test_gate_errors_when_ledger_missing(tmp_path) -> None:
    assert _run_governance(str(tmp_path)) == 2  # no provenance.jsonl to audit
