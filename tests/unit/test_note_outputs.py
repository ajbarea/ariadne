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
    import json

    from ariadne.profiles import Envelope, Profile
    from ariadne.provenance.citations import validate_citations
    from ariadne.provenance.governance import audit_read_only
    from ariadne.provenance.ledger import ProvenanceLedger
    from ariadne.report.note import write_outputs

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
