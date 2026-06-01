from __future__ import annotations

from ariadne.provenance.citations import (
    CitationReport,
    extract_citations,
    validate_citations,
)
from ariadne.provenance.ledger import ProvenanceLedger


def test_extract_citations_finds_unique_ids_in_order() -> None:
    note = "Alpha reports to Bravo [cite:g1]. Bravo leads Unit-7 [cite:g2]. Recap [cite:g1]."
    assert extract_citations(note) == ["g1", "g2"]


def test_validate_passes_when_all_citations_resolve() -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q1"}, "r")
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q2"}, "r")
    report = validate_citations("Fact A [cite:g1]. Fact B [cite:g2].", led)
    assert isinstance(report, CitationReport)
    assert report.ok is True
    assert report.dangling == []
    assert report.unused == []


def test_validate_flags_dangling_citation() -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q1"}, "r")
    report = validate_citations("Real [cite:g1]. Fake [cite:g9].", led)
    assert report.ok is False
    assert report.dangling == ["g9"]


def test_validate_reports_unused_evidence() -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q1"}, "r")
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q2"}, "r")
    report = validate_citations("Only one fact [cite:g1].", led)
    assert report.ok is True  # unused is informational, not a failure
    assert report.unused == ["g2"]
