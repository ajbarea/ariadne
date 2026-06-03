from __future__ import annotations

import json

from ariadne.provenance.citations import validate_citations
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
