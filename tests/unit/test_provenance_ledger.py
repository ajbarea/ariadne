from __future__ import annotations

import json

from ariadne.provenance.ledger import ProvenanceLedger


def test_record_assigns_sequential_ids() -> None:
    led = ProvenanceLedger()
    k1 = led.record("mcp__neo4j__read_neo4j_cypher", {"query": "MATCH (n) RETURN n"}, "rows...")
    k2 = led.record("mcp__neo4j__get_neo4j_schema", {}, "schema...")
    assert k1 == "g1"
    assert k2 == "g2"
    assert led.has("g1") and led.has("g2")
    assert not led.has("g3")


def test_entries_capture_tool_input_and_response() -> None:
    led = ProvenanceLedger()
    led.record("mcp__neo4j__read_neo4j_cypher", {"query": "Q"}, "RESP")
    (entry,) = led.entries
    assert entry["id"] == "g1"
    assert entry["tool"] == "mcp__neo4j__read_neo4j_cypher"
    assert entry["tool_input"] == {"query": "Q"}
    assert "RESP" in entry["response_excerpt"]
    assert "ts" in entry


def test_response_excerpt_is_truncated() -> None:
    led = ProvenanceLedger(excerpt_chars=10)
    led.record("t", {}, "x" * 500)
    assert len(led.entries[0]["response_excerpt"]) <= 10


def test_write_jsonl_round_trips(tmp_path) -> None:
    led = ProvenanceLedger()
    led.record("t", {"a": 1}, "r")
    path = tmp_path / "provenance.jsonl"
    led.write_jsonl(path)
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["id"] == "g1"


def test_read_jsonl_round_trips(tmp_path) -> None:
    led = ProvenanceLedger()
    led.record("t", {"a": 1}, "r")
    path = tmp_path / "provenance.jsonl"
    led.write_jsonl(path)
    assert ProvenanceLedger.read_jsonl(path) == led.entries


def test_read_jsonl_skips_blank_lines(tmp_path) -> None:
    path = tmp_path / "provenance.jsonl"
    path.write_text('{"id": "g1"}\n\n{"id": "g2"}\n', encoding="utf-8")
    assert [e["id"] for e in ProvenanceLedger.read_jsonl(path)] == ["g1", "g2"]
