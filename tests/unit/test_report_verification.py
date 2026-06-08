"""Verification-UX hardening of the workup report (analyst-facing).

The report is the surface on which a human analyst *verifies* the agent's work:
click a ``[cite:gN]`` chip, read the exact query and what it returned, judge whether
the claim holds. These tests cover three things that make or break that loop —
readable evidence (unwrap the MCP transport envelope), truncation transparency
(never show a silently-cut excerpt as if it were whole), and re-runnability (the
analyst can copy the exact query to run it themselves).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ariadne.report.html import _clean_evidence, extract_report_data, render_report

if TYPE_CHECKING:
    from pathlib import Path


# ---- Evidence readability: unwrap the MCP tool-result envelope ----


def test_clean_evidence_unwraps_json_mcp_envelope() -> None:
    """A JSON MCP envelope (postgres) shows the inner data, not the transport wrapper."""
    raw = json.dumps(
        {
            "result": [{"type": "text", "text": '[{"alias": "H1", "name": "Halberd"}]'}],
            "annotations": None,
            "_meta": None,
        }
    )
    out = _clean_evidence(raw)
    assert "Halberd" in out
    assert "_meta" not in out
    assert "annotations" not in out
    assert '"type": "text"' not in out


def test_clean_evidence_unwraps_python_repr_envelope() -> None:
    """A Python-repr list envelope (neo4j) is unwrapped too (single-quoted, not JSON)."""
    raw = "[{'type': 'text', 'text': '[{\"labels\": [\"Unit\", \"Person\"]}]'}]"
    out = _clean_evidence(raw)
    assert "Unit" in out and "Person" in out
    assert "'type'" not in out


def test_clean_evidence_pretty_prints_inner_json() -> None:
    """Inner JSON is indented so an analyst can read rows, not a one-line blob."""
    raw = json.dumps({"result": [{"type": "text", "text": '[{"a": 1, "b": 2}]'}]})
    out = _clean_evidence(raw)
    assert "\n" in out  # multi-line, indented


def test_clean_evidence_joins_multiple_text_parts() -> None:
    raw = json.dumps(
        {"result": [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}]}
    )
    out = _clean_evidence(raw)
    assert "first" in out and "second" in out


def test_clean_evidence_returns_raw_when_not_an_envelope() -> None:
    """Plain text (or anything unparseable) passes through unchanged — never lose data."""
    assert _clean_evidence("Halberd, Signals-Cell") == "Halberd, Signals-Cell"
    assert _clean_evidence("") == ""


def test_extract_cleans_excerpt_but_keeps_raw(tmp_path: Path) -> None:
    """The report payload carries cleaned evidence for display + the raw wire bytes."""
    raw = json.dumps({"result": [{"type": "text", "text": '[{"alias": "H1"}]'}]})
    _write_workup(tmp_path, excerpt=raw)
    data = extract_report_data(tmp_path)
    entry = data["ledger"][0]
    assert "H1" in entry["excerpt"]
    assert "_meta" not in entry["excerpt"]
    assert entry["excerpt_raw"] == raw  # the literal response is still available


# ---- Truncation transparency ----


def test_extract_flags_truncated_evidence(tmp_path: Path) -> None:
    """When the ledger recorded the original length and it exceeds the excerpt, say so."""
    _write_workup(tmp_path, excerpt="x" * 2000, full_len=5432)
    data = extract_report_data(tmp_path)
    entry = data["ledger"][0]
    assert entry["truncated"] is True
    assert entry["full_len"] == 5432


def test_extract_not_truncated_without_full_len(tmp_path: Path) -> None:
    """No original-length metadata (or it matches) ⇒ not flagged as truncated."""
    _write_workup(tmp_path, excerpt="short evidence")
    data = extract_report_data(tmp_path)
    assert data["ledger"][0]["truncated"] is False


def test_report_surfaces_truncation_notice(tmp_path: Path) -> None:
    """The rendered drawer warns the analyst that evidence was cut (don't trust a partial).

    Asserts the *visible* notice markup, not the ``"truncated":true`` data-island field
    (which would pass trivially without the feature).
    """
    _write_workup(tmp_path, excerpt="x" * 2000, full_len=5432)
    html = render_report(tmp_path)
    assert "evidence truncated" in html.lower()  # the analyst-facing phrasing
    assert "evtrunc" in html  # the notice element the drawer renders


# ---- Re-runnability: copy the exact query ----


def test_report_has_copy_query_affordance(tmp_path: Path) -> None:
    """The drawer offers a copy control so the analyst can re-run the query independently."""
    _write_workup(tmp_path, excerpt="data")
    html = render_report(tmp_path)
    assert "clipboard" in html.lower()
    assert "copy" in html.lower()


def _write_workup(tmp_path: Path, *, excerpt: str, full_len: int | None = None) -> None:
    (tmp_path / "note.md").write_text(
        "## Summary\nHalberd leads the Signals-Cell [cite:g1].\n", encoding="utf-8"
    )
    entry: dict = {
        "id": "g1",
        "tool": "mcp__neo4j__read_neo4j_cypher",
        "tool_input": {"query": "MATCH (p:Person {name:'Halberd'}) RETURN p"},
        "response_excerpt": excerpt,
    }
    if full_len is not None:
        entry["response_full_len"] = full_len
    (tmp_path / "provenance.jsonl").write_text(json.dumps(entry), encoding="utf-8")
    (tmp_path / "citations.json").write_text(
        json.dumps({"entity": "Halberd", "ok": True, "cited": ["g1"], "dangling": []}),
        encoding="utf-8",
    )
