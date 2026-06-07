from __future__ import annotations

import json

from ariadne.provenance.citations import validate_citations
from ariadne.provenance.governance import audit_read_only
from ariadne.provenance.ledger import ProvenanceLedger
from ariadne.provenance.tradecraft import lint_estimative_language
from ariadne.report.note import write_outputs


def test_write_outputs_creates_all_three_files(tmp_path) -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q"}, "r")
    note = "Finding [cite:g1]."
    report = validate_citations(note, led)

    write_outputs(tmp_path, entity="Alpha", note=note, ledger=led, report=report)

    assert (tmp_path / "note.md").read_text() == note
    assert (tmp_path / "provenance.jsonl").read_text().strip()
    citations = json.loads((tmp_path / "citations.json").read_text())
    assert citations["ok"] is True
    assert citations["cited"] == ["g1"]
    assert citations["entity"] == "Alpha"
    assert not (tmp_path / "tradecraft.json").exists()  # not written unless provided
    assert not (tmp_path / "governance.json").exists()  # not written unless provided


def test_write_outputs_writes_governance_when_provided(tmp_path) -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "MATCH (n) RETURN n"}, "r")
    note = "Finding [cite:g1]."
    report = validate_citations(note, led)
    governance = audit_read_only(led.entries)

    write_outputs(
        tmp_path, entity="Alpha", note=note, ledger=led, report=report, governance=governance
    )

    gov = json.loads((tmp_path / "governance.json").read_text())
    assert gov["ok"] is True
    assert gov["write_attempts"] == []


def test_write_outputs_writes_tradecraft_when_provided(tmp_path) -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q"}, "r")
    note = "Halberd is likely the cell lead [cite:g1]."
    report = validate_citations(note, led)
    tradecraft = lint_estimative_language(note)

    write_outputs(
        tmp_path, entity="Alpha", note=note, ledger=led, report=report, tradecraft=tradecraft
    )

    tc = json.loads((tmp_path / "tradecraft.json").read_text())
    assert ["likely", "55-80%"] in tc["standard_terms"]


def test_governance_json_records_profile(tmp_path) -> None:
    from ariadne.profiles import Envelope, Profile

    ledger = ProvenanceLedger()
    gov = audit_read_only(ledger.entries)
    report = validate_citations("", ledger)
    prof = Profile(
        name="fast-local",
        model="fast-local",
        egress="none",
        envelope=Envelope(max_turns=12, max_thinking_tokens=0),
    )
    write_outputs(
        tmp_path, entity="X", note="", ledger=ledger, report=report, governance=gov, profile=prof
    )
    payload = json.loads((tmp_path / "governance.json").read_text())
    assert payload["profile"]["name"] == "fast-local"
    assert payload["profile"]["egress"] == "none"
    assert payload["profile"]["max_turns"] == 12
    assert payload["profile"]["max_thinking_tokens"] == 0


def test_write_outputs_persists_repair_coverage_gain(tmp_path) -> None:
    # The repair loop's measured gain lands in citations.json (ADR-0023): raw G-Cite
    # baseline -> post-repair coverage, the Δ, and the covered/total counts + passes.
    from ariadne.provenance.citations import citation_coverage

    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q"}, "r")
    note = "Finding [cite:g1]. A second grounded point [cite:g1]."
    report = validate_citations(note, led)
    before = citation_coverage("Finding [cite:g1]. A second point with no cite.")
    after = citation_coverage(note)

    write_outputs(
        tmp_path,
        entity="Alpha",
        note=note,
        ledger=led,
        report=report,
        coverage_before=before,
        coverage_after=after,
        repair_passes=1,
    )

    cov = json.loads((tmp_path / "citations.json").read_text())["coverage"]
    assert cov["before"] == before.fraction == 0.5
    assert cov["after"] == after.fraction == 1.0
    assert cov["gain"] == 0.5
    assert (cov["covered"], cov["total"]) == (after.covered, after.total)
    assert cov["passes"] == 1


def test_write_outputs_coverage_gain_is_null_without_repair(tmp_path) -> None:
    # --no-repair persists a single coverage with gain=null (repair did not run),
    # distinct from gain=0.0 (repair ran, found nothing to fix).
    from ariadne.provenance.citations import citation_coverage

    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q"}, "r")
    note = "Finding [cite:g1]."
    report = validate_citations(note, led)

    write_outputs(
        tmp_path,
        entity="Alpha",
        note=note,
        ledger=led,
        report=report,
        coverage_after=citation_coverage(note),
    )

    cov = json.loads((tmp_path / "citations.json").read_text())["coverage"]
    assert cov["after"] == 1.0
    assert cov["before"] is None
    assert cov["gain"] is None
    assert cov["passes"] is None
