from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ariadne.report.html import (
    _render_note_html,
    extract_report_data,
    render_report,
    write_report,
)

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


def test_note_splits_into_collapsible_sections(tmp_path: Path) -> None:
    d = tmp_path
    (d / "note.md").write_text(
        "# Analytic note: Halberd\n## Summary\nHalberd leads [cite:g1].\n"
        "## Provenance\n- g1 — located Halberd.\n",
        encoding="utf-8",
    )
    (d / "provenance.jsonl").write_text("", encoding="utf-8")
    (d / "citations.json").write_text(json.dumps({"entity": "Halberd"}), encoding="utf-8")
    note_html = extract_report_data(d)["note_html"]
    assert '<details class="nsec"' in note_html  # sections are collapsible components
    assert "<summary>Summary</summary>" in note_html
    # the verbose Provenance section defaults collapsed (no `open`)
    assert '<details class="nsec"><summary>Provenance</summary>' in note_html
    assert '<details class="nsec" open><summary>Summary</summary>' in note_html
    # chevron uses a valid CSS unicode escape (single backslash, not a raw-string double)
    html = render_report(d)
    assert 'content:"\\25B8"' in html and 'content:"\\\\25B8"' not in html


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


def test_uncited_claim_is_spotlighted_in_the_note(tmp_path: Path) -> None:
    d = tmp_path
    (d / "note.md").write_text(
        "## Summary\nHalberd leads the Signals-Cell [cite:g1].\n"
        "Decisive finding: the coordination is deliberate.\n",
        encoding="utf-8",
    )
    (d / "provenance.jsonl").write_text(
        json.dumps(
            {
                "id": "g1",
                "tool": "mcp__neo4j__read_neo4j_cypher",
                "tool_input": {"query": "x"},
                "response_excerpt": "y",
            }
        ),
        encoding="utf-8",
    )
    (d / "citations.json").write_text(
        json.dumps(
            {
                "entity": "Halberd",
                "ok": False,
                "cited": ["g1"],
                "dangling": [],
                "unused": [],
                "uncited": ["Decisive finding: the coordination is deliberate."],
            }
        ),
        encoding="utf-8",
    )
    html = render_report(d)
    # the uncited claim text reaches the data island so the JS can locate it
    assert "Decisive finding: the coordination is deliberate." in html
    # the spotlight class + the wiring that reads the uncited list both exist
    assert "uncited-claim" in html
    assert "DATA.citations.uncited" in html or "citations.uncited" in html


def test_report_renders_evaluation_panel_when_scored(tmp_path: Path) -> None:
    d = _make_workup(tmp_path)
    (d / "eval.json").write_text(
        json.dumps(
            {
                "fixture": "halberd",
                "entity": "Halberd",
                "recall": 1.0,
                "trajectory": 1.0,
                "grounded": True,
                "pivot_burden": 1.0,
                "queries_run": 3,
                "supporting_fact_precision": 1.0,
                "supporting_fact_recall": 0.33,
                "supporting_fact_f1": 0.5,
                "context_utilization": 0.67,
                "citation_coverage": 0.83,
            }
        ),
        encoding="utf-8",
    )
    (d / "rubric.json").write_text(
        json.dumps(
            {
                "overall": 4.5,
                "dimensions": [
                    {
                        "key": "alternatives",
                        "score": 5,
                        "rationale": "ACH on the decisive finding.",
                    },
                    {"key": "argumentation", "score": 4, "rationale": "Logic mostly sound."},
                ],
            }
        ),
        encoding="utf-8",
    )
    data = extract_report_data(d)
    assert data["evaluation"]["grounded"] is True
    assert data["rubric"]["overall"] == 4.5
    html = render_report(d)
    assert "Analytic evaluation" in html  # the panel heading
    assert "ACH on the decisive finding" in html  # a rubric rationale is shown
    assert "halberd" in html  # the fixture is named
    assert "EV.citation_coverage" in html  # final-note coverage wired into the eval panel


def test_report_omits_evaluation_data_when_not_scored(tmp_path: Path) -> None:
    # Most live workups have no fixture/judge run — the panel must degrade cleanly.
    data = extract_report_data(_make_workup(tmp_path))
    assert data["evaluation"] is None
    assert data["rubric"] is None


def test_report_surfaces_context_utilization(tmp_path: Path) -> None:
    # ADR-0019: a descriptive retrieval-side stat — fraction of retrieved evidence
    # that grounded a cited claim — reported as a dashboard card, never gated.
    d = _make_workup(tmp_path)  # note cites g1 + g2; ledger has g1 + g2 → utilization 1.0
    data = extract_report_data(d)
    assert data["utilization"] == 1.0
    html = render_report(d)
    assert "Context utilization" in html  # the dashboard card label
    # the plain-language definition names the exploratory-retrieval caveat
    assert "exploratory" in html.lower()


def test_report_surfaces_repair_coverage_gain(tmp_path: Path) -> None:
    # ADR-0023: the P-Cite repair loop's measured coverage gain — raw G-Cite draft
    # to repaired coverage — is a dashboard card (descriptive, never gated).
    d = _make_workup(tmp_path)
    (d / "citations.json").write_text(
        json.dumps(
            {
                "entity": "Halberd",
                "ok": True,
                "cited": ["g1", "g2"],
                "dangling": [],
                "unused": [],
                "uncited": [],
                "coverage": {
                    "before": 0.5,
                    "after": 1.0,
                    "gain": 0.5,
                    "covered": 2,
                    "total": 2,
                    "passes": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    data = extract_report_data(d)
    # the before/after/gain values reach the data island so the dashboard JS can render them
    assert data["citations"]["coverage"] == {
        "before": 0.5,
        "after": 1.0,
        "gain": 0.5,
        "covered": 2,
        "total": 2,
        "passes": 1,
    }
    html = render_report(d)
    assert "Citation coverage" in html  # the dashboard card label
    assert "structural coverage" in html.lower()  # the descriptive definition
    # the card must be WIRED INTO the dashboard array, not merely defined — a
    # defined-but-unlisted covStat renders nothing (caught headlessly once already).
    assert "covStat," in html  # array membership; computed render is verified headlessly


def test_entity_network_node_has_a_detail_drawer(tmp_path: Path) -> None:
    d = _make_workup(tmp_path)
    (d / "subgraph.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "label": "Person",
                        "name": "Halberd",
                        "target": True,
                        "props": {"role": "cell lead", "clearance": "TS"},
                    },
                    {"id": "n2", "label": "Unit", "name": "Signals-Cell", "target": False},
                ],
                "edges": [{"src": "n1", "dst": "n2", "type": "MEMBER_OF"}],
            }
        ),
        encoding="utf-8",
    )
    html = render_report(d)
    # a dedicated entity-detail drawer mirroring the evidence drawer, plus its handler
    assert 'id="edrawer"' in html
    assert "selectEntity" in html
    # node attributes survive into the data island so the drawer can render them
    assert "clearance" in html and "cell lead" in html


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


def test_note_renders_a_gfm_table_not_raw_pipes() -> None:
    note = (
        "## Top correspondents\n"
        "| Contact | Count |\n"
        "|---|---|\n"
        "| vkaminski@aol.com | 1,007 |\n"
        "| shirley.crenshaw@enron.com | 456 |\n"
    )
    html = _render_note_html(note)
    assert "<table" in html
    assert "<th" in html and "Contact" in html and "Count" in html
    assert "<td" in html and "vkaminski@aol.com" in html and "1,007" in html
    # the raw markdown must NOT leak as paragraph text
    assert "|---|" not in html
    assert "<p>| Contact" not in html and "| vkaminski" not in html


def test_table_cells_render_cites_and_column_alignment() -> None:
    note = "| Who | Count |\n|:---|---:|\n| see [cite:g18] | 5 |\n"
    html = _render_note_html(note)
    assert 'data-cite="g18"' in html  # cites stay clickable inside a cell
    assert "text-align:right" in html  # the ---: column is right-aligned
    assert "text-align:left" in html  # the :--- column is left-aligned


def test_inline_code_spans_render_as_code_not_literal_backticks() -> None:
    html = _render_note_html("Aggregated by `count`; variant `vkaminskji@aol.com` appears.\n")
    assert "<code>count</code>" in html
    assert "<code>vkaminskji@aol.com</code>" in html
    assert "`count`" not in html  # no literal backticks leak through


def test_a_lone_pipe_line_is_not_mistaken_for_a_table() -> None:
    # Prose that merely contains a pipe (no |---| separator) stays a paragraph.
    html = _render_note_html("The flag is a|b in the config.\n")
    assert "<table" not in html
    assert "a|b" in html


def test_cite_only_header_column_becomes_a_caption_not_a_phantom_column() -> None:
    """An agent that stuffs a table-level citation into a header cell (real Enron note bug)
    leaves a header column with no body beneath it. Drop the phantom column and hoist the
    citation to a caption so it stays clickable instead of rendering an empty third column."""
    note = (
        "## Top correspondents\n"
        "| Contact | Count | [cite:g18] |\n"
        "|---|---|---|\n"
        "| vkaminski@aol.com | 1,007 |\n"
        "| shirley.crenshaw@enron.com | 456 |\n"
    )
    html = _render_note_html(note)
    assert html.count("</th>") == 2  # the phantom 3rd column is gone
    assert html.count("</td>") == 4  # two rows x two real columns, no empty filler cells
    assert 'class="tcap"' in html  # citation hoisted to a caption
    assert 'data-cite="g18"' in html  # and still a clickable chip


def test_cite_only_header_is_kept_when_the_column_has_data() -> None:
    """A cite-only header over a populated column is a real column, not an artifact — keep it."""
    html = _render_note_html("## T\n| A | [cite:g1] |\n|---|---|\n| x | y |\n")
    assert html.count("</th>") == 2  # both columns kept
    assert 'class="tcap"' not in html


def test_write_report_emits_report_html(tmp_path: Path) -> None:
    out = write_report(_make_workup(tmp_path))
    assert out == tmp_path / "report.html"
    assert out.exists()
    assert "Halberd" in out.read_text(encoding="utf-8")
