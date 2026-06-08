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


def _write_full_workup(tmp_path: Path, note: str) -> None:
    """A realistic workup dir: ledger + all four signal artifacts, via write_outputs."""
    from ariadne.profiles import Envelope, Profile
    from ariadne.provenance.citations import citation_coverage, validate_citations
    from ariadne.provenance.governance import audit_read_only
    from ariadne.provenance.tradecraft import lint_estimative_language
    from ariadne.report.note import write_outputs

    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "MATCH (n) RETURN n"}, "rows...")
    report = validate_citations(note, led)
    write_outputs(
        tmp_path,
        entity="Halberd",
        note=note,
        ledger=led,
        report=report,
        tradecraft=lint_estimative_language(note),
        governance=audit_read_only(led.entries),
        profile=Profile(name="default", model="m", egress="enclave", envelope=Envelope()),
        coverage_after=citation_coverage(note),
    )


def test_unified_verdict_is_printed_for_a_full_workup(tmp_path, capsys) -> None:
    _write_full_workup(tmp_path, "Halberd is likely the cell lead [cite:g1]. Low confidence.")
    rc = _run_governance(str(tmp_path))
    out = capsys.readouterr().out
    assert rc == 0
    # The folded multi-axis label surfaces every governance pillar, not just read-only.
    assert "Read-only contract" in out
    assert "Citation gate" in out
    assert "ICD-203" in out
    assert "Egress posture" in out


def test_unified_gate_fails_exit_one_on_a_persisted_citation_failure(tmp_path) -> None:
    # An uncited claim makes the citation axis FAIL → the weakest-link gate exits 1
    # (analytic), distinct from the read-only breach's exit 3 (security).
    _write_full_workup(tmp_path, "Halberd leads the cell. A second uncited claim here.")
    assert _run_governance(str(tmp_path)) == 1


def test_read_only_breach_still_takes_exit_three_precedence(tmp_path) -> None:
    # Security breach outranks an analytic miss even with the full verdict in play.
    _write_full_workup(tmp_path, "A claim with no citation at all.")
    _write_ledger(tmp_path, {"query": "CREATE (p:Person {name:'X'})"})
    assert _run_governance(str(tmp_path)) == 3
