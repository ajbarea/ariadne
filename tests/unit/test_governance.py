"""Hermetic tests for the read-only governance audit.

The brief requires governance uniform across quality / security / data
integrity. Quality is covered by the citation gate, the tradecraft lint, and the
ICD-203 rubric. This audits the **security / data-integrity** axis: the analytic
loop must stay read-only, so any mutating statement in the provenance ledger — a
write the agent issued, even one the connector blocked — is a contract violation.
"""

from __future__ import annotations

from ariadne.provenance.governance import audit_read_only


def _entry(gid: str, **tool_input: str) -> dict:
    return {"id": gid, "tool_input": tool_input}


def test_read_only_ledger_passes() -> None:
    entries = [
        _entry("g1", query="MATCH (p:Person {name:'Halberd'}) RETURN p"),
        _entry("g2", sql="SELECT * FROM personnel WHERE name = 'Halberd'"),
    ]
    report = audit_read_only(entries)
    assert report.ok is True
    assert report.write_attempts == []


def test_cypher_write_is_flagged() -> None:
    entries = [_entry("g1", query="CREATE (p:Person {name:'X'}) RETURN p")]
    report = audit_read_only(entries)
    assert report.ok is False
    assert report.write_attempts[0]["id"] == "g1"
    assert report.write_attempts[0]["verb"] == "CREATE"


def test_sql_write_is_flagged() -> None:
    entries = [_entry("g3", sql="DELETE FROM personnel WHERE alias = 'H1'")]
    report = audit_read_only(entries)
    assert report.ok is False
    assert report.write_attempts[0]["verb"] == "DELETE"


def test_mid_statement_cypher_set_is_flagged() -> None:
    # Cypher mutations need not lead the statement (MATCH ... SET ...).
    entries = [_entry("g1", query="MATCH (p:Person {name:'Halberd'}) SET p.role = 'lead'")]
    report = audit_read_only(entries)
    assert report.ok is False
    assert report.write_attempts[0]["verb"] == "SET"


def test_read_verbs_in_column_names_do_not_false_positive() -> None:
    # 'created_at' / 'subset' must not trip the word-boundary matcher.
    entries = [
        _entry("g1", sql="SELECT created_at, subset_id FROM personnel"),
        _entry("g2", query="MATCH (n) WHERE n.offset = 1 RETURN n"),
    ]
    assert audit_read_only(entries).ok is True


def test_every_write_attempt_is_reported() -> None:
    entries = [
        _entry("g1", query="MATCH (n) RETURN n"),
        _entry("g2", sql="UPDATE personnel SET clearance = 'TOP SECRET'"),
        _entry("g3", query="MERGE (p:Person {name:'Y'})"),
    ]
    report = audit_read_only(entries)
    assert {w["id"] for w in report.write_attempts} == {"g2", "g3"}
