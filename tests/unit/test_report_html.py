from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ariadne.report.html import extract_report_data, render_report, write_report

if TYPE_CHECKING:
    from pathlib import Path


def _make_workup(tmp_path: Path) -> Path:
    (tmp_path / "note.md").write_text(
        "## Summary\nHalberd leads the Signals-Cell [cite:g1]. "
        "The dyad with Talon is decisive [cite:g2].\n",
        encoding="utf-8",
    )
    ledger = [
        {
            "id": "g1",
            "tool": "mcp__neo4j__read_neo4j_cypher",
            "tool_input": {"query": "MATCH (p:Person {name:'Halberd'}) RETURN p"},
            "response_excerpt": "Halberd, Signals-Cell",
        },
        {
            "id": "g2",
            "tool": "mcp__postgres__query",
            "tool_input": {"sql": "SELECT * FROM personnel"},
            "response_excerpt": "Talon row",
        },
    ]
    (tmp_path / "provenance.jsonl").write_text(
        "\n".join(json.dumps(e) for e in ledger), encoding="utf-8"
    )
    (tmp_path / "citations.json").write_text(
        json.dumps(
            {"entity": "Halberd", "ok": True, "cited": ["g1", "g2"], "dangling": [], "unused": []}
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_extract_pulls_entity_note_and_ledger(tmp_path: Path) -> None:
    data = extract_report_data(_make_workup(tmp_path))
    assert data["entity"] == "Halberd"
    assert len(data["ledger"]) == 2
    # source is derived from the tool prefix
    by_id = {e["id"]: e for e in data["ledger"]}
    assert by_id["g1"]["source"] == "graph"
    assert by_id["g2"]["source"] == "relational"
    assert "MATCH" in by_id["g1"]["query"]
    # note rendered to HTML with clickable cite chips
    assert 'data-cite="g1"' in data["note_html"]


def test_render_is_self_contained_html_with_data_island(tmp_path: Path) -> None:
    html = render_report(_make_workup(tmp_path))
    assert html.lstrip().lower().startswith("<!doctype html")
    assert "Halberd" in html
    # data embedded inline as a JSON island; no external network *loads*
    # (the SVG xmlns URI is a namespace, not a request — so check load points).
    assert 'id="ariadne-report-data"' in html
    assert 'src="http' not in html
    assert 'href="http' not in html
    assert "@import" not in html
    assert "url(http" not in html
    # clickable provenance + evidence are embedded so it all resolves offline
    assert "data-cite" in html and "g1" in html
    assert "MATCH" in html


def test_render_has_a_light_dark_theme_toggle(tmp_path: Path) -> None:
    html = render_report(_make_workup(tmp_path))
    # a toggle control + a light-theme override + persistence so the choice sticks
    assert 'id="theme-toggle"' in html
    assert "[data-theme=light]" in html or '[data-theme="light"]' in html
    assert "localStorage" in html


def test_dashboard_cards_carry_plain_language_definitions(tmp_path: Path) -> None:
    html = render_report(_make_workup(tmp_path))
    assert "statdef" in html  # expandable definition element
    assert "estimative language" in html  # the ICD-203 explanation in analyst terms


def test_entity_network_renders_when_subgraph_present(tmp_path: Path) -> None:
    d = _make_workup(tmp_path)
    (d / "subgraph.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {"id": "n1", "label": "Person", "name": "Halberd", "target": True},
                    {"id": "n2", "label": "Unit", "name": "Signals-Cell", "target": False},
                ],
                "edges": [{"src": "n1", "dst": "n2", "type": "MEMBER_OF"}],
            }
        ),
        encoding="utf-8",
    )
    html = render_report(d)
    assert "Entity network" in html  # the tab
    assert "Signals-Cell" in html and "MEMBER_OF" in html  # real entities + relationship


def test_reconciliation_panel_classifies_corroboration_and_conflict(tmp_path: Path) -> None:
    d = tmp_path
    (d / "note.md").write_text(
        "## Relationships\n"
        "Halberd and Wren are consistent across both stores [cite:g1]. "
        "Talon's location conflicts: the personnel record disagrees with the graph [cite:g2].\n",
        encoding="utf-8",
    )
    (d / "provenance.jsonl").write_text("", encoding="utf-8")
    (d / "citations.json").write_text(json.dumps({"entity": "Halberd"}), encoding="utf-8")
    data = extract_report_data(d)
    rec = data["reconciliation"]
    assert any("consistent across both" in s.lower() for s in rec["corroborations"])
    assert any("conflicts" in s.lower() or "disagrees" in s.lower() for s in rec["conflicts"])
    html = render_report(d)
    assert "Reconciliation" in html and "corroborat" in html.lower()


def test_write_report_emits_report_html(tmp_path: Path) -> None:
    out = write_report(_make_workup(tmp_path))
    assert out == tmp_path / "report.html"
    assert out.exists()
    assert "Halberd" in out.read_text(encoding="utf-8")
