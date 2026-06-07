"""Phase 4 eval harness — planted-needle scoring against the seed fixture."""

from __future__ import annotations

import json

from ariadne.evaluation.needle import (
    HALBERD_FIXTURE,
    WREN_TIE_FIXTURE,
    EvalReport,
    NeedleFixture,
    SupportingFact,
    score_workup,
    score_workup_dir,
)


def _fixture_with_facts(*facts: SupportingFact) -> NeedleFixture:
    return NeedleFixture(
        entity="X",
        answer_markers=(),
        traversal_markers=(),
        min_hops=1,
        supporting_facts=facts,
    )


def _entry(query: str) -> dict:
    return {
        "id": "g1",
        "tool": "mcp__neo4j__read_neo4j_cypher",
        "tool_input": {"query": query},
        "response_excerpt": "r",
    }


def _sql_entry(sql: str) -> dict:
    return {
        "id": "g2",
        "tool": "mcp__postgres__execute_sql",
        "tool_input": {"sql": sql},  # postgres-mcp names its arg `sql`, not `query`
        "response_excerpt": "r",
    }


def test_recall_counts_surfaced_answer_markers() -> None:
    note = "The bridge runs through Compound-Alpha; the units are co-located."
    report = score_workup(note, [_entry("CO_LOCATED Compound-Alpha")], HALBERD_FIXTURE)
    assert isinstance(report, EvalReport)
    assert report.recall == 1.0


def test_trajectory_requires_traversal_in_the_ledger_queries() -> None:
    note = "Compound-Alpha — the units are co-located."
    entries = [
        _entry("MATCH (p:Person {name:'Halberd'})-[:MEMBER_OF]->(u:Unit)"),
        _entry("MATCH (s:Site {name:'Compound-Alpha'})-[:CO_LOCATED]-(x)"),
    ]
    report = score_workup(note, entries, HALBERD_FIXTURE)
    assert report.trajectory == 1.0
    assert report.grounded is True


def test_naming_the_needle_without_traversing_is_a_guess() -> None:
    # The note surfaces the bridge (recall 1) but the ledger never walked it.
    note = "Halberd is co-located at Compound-Alpha."
    entries = [_entry("MATCH (p:Person {name:'Halberd'}) RETURN p")]
    report = score_workup(note, entries, HALBERD_FIXTURE)
    assert report.recall == 1.0
    assert report.trajectory < 1.0
    assert report.grounded is False


def test_report_carries_context_utilization_over_the_ledger() -> None:
    # Fixture-independent descriptive stat (ADR-0019): of the distinct evidence
    # retrieved, the fraction that grounded a cited claim. g3 is an uncited
    # exploratory call, so utilization is 2/3 — and never gates `grounded`.
    note = "Compound-Alpha, co-located [cite:g1]; the tie holds [cite:g2]."
    entries = [
        {"id": "g1", "tool_input": {"query": "MEMBER_OF CO_LOCATED"}},
        {"id": "g2", "tool_input": {"query": "x"}},
        {"id": "g3", "tool_input": {"query": "negative check"}},
    ]
    report = score_workup(note, entries, HALBERD_FIXTURE)
    assert report.context_utilization == 2 / 3


def test_report_carries_citation_coverage_of_the_note() -> None:
    # Fixture-independent structural coverage (ADR-0023): of the note's citable
    # claims, the fraction carrying a citation. Descriptive, like context_utilization;
    # surfaced across datasets by `ariadne eval`. The ledger is irrelevant (note-only).
    note = "Halberd leads Signals-Cell [cite:g1]. He also secretly runs Talon."
    report = score_workup(note, [_entry("CO_LOCATED Compound-Alpha")], HALBERD_FIXTURE)
    assert report.citation_coverage == 0.5  # one of two claims cited


def test_trajectory_credits_traversal_seen_in_the_observation() -> None:
    # ADR-0024: an untyped `-[r]- RETURN type(r)` query walks the bridge but names the
    # rel types only in the RESPONSE. Trajectory must credit that, not call it a guess.
    note = "Halberd's Signals-Cell is co-located with Compound-Alpha."  # surfaces the needle
    entries = [
        {
            "tool": "mcp__neo4j__read_neo4j_cypher",
            "tool_input": {"query": "MATCH (h:Person {name:'Halberd'})-[r]-(o) RETURN type(r)"},
            "response_excerpt": '[{"rel":"MEMBER_OF","oname":"Signals-Cell"}]',
        },
        {
            "tool": "mcp__neo4j__read_neo4j_cypher",
            "tool_input": {"query": "MATCH (u:Unit {name:'Signals-Cell'})-[r]-(o) RETURN type(r)"},
            "response_excerpt": '[{"rel":"CO_LOCATED","oname":"Compound-Alpha"}]',
        },
    ]
    report = score_workup(note, entries, HALBERD_FIXTURE)
    assert report.trajectory == 1.0
    assert report.grounded is True


def test_schema_introspection_alone_is_not_traversal() -> None:
    # `CALL db.relationshipTypes()` lists every rel type — catalog enumeration, not
    # walking Halberd's path. It must NOT credit trajectory (a guess stays a guess).
    note = "Halberd's Signals-Cell is co-located with Compound-Alpha."  # surfaced, not walked
    entries = [
        {
            "tool": "mcp__neo4j__read_neo4j_cypher",
            "tool_input": {
                "query": "CALL db.relationshipTypes() YIELD relationshipType "
                "RETURN collect(relationshipType)"
            },
            "response_excerpt": '["MEMBER_OF","CO_LOCATED","REPORTS_TO"]',
        },
    ]
    report = score_workup(note, entries, HALBERD_FIXTURE)
    assert report.trajectory == 0.0
    assert report.grounded is False


def test_traversal_counts_even_when_the_bridge_node_is_not_named_in_a_query() -> None:
    # The agent reaches the bridge node via relationships (a shortest path / *..4
    # hop) without querying it by name — the relationship types are the evidence
    # of traversal; the node name in the note is recall, checked separately.
    note = "Halberd is co-located at Compound-Alpha with Wren."
    entries = [
        _entry("MATCH (h:Person {name:'Halberd'})-[:MEMBER_OF]->(:Unit)-[:CO_LOCATED]-(s) RETURN s")
    ]
    report = score_workup(note, entries, HALBERD_FIXTURE)
    assert report.trajectory == 1.0
    assert report.grounded is True


def test_pivot_burden_is_queries_over_true_hops() -> None:
    entries = [_entry("q") for _ in range(6)]
    report = score_workup("Compound-Alpha co-located", entries, HALBERD_FIXTURE)
    assert report.queries_run == 6
    assert report.pivot_burden == 6 / 3


def test_eval_subcommand_returns_zero_when_grounded(tmp_path) -> None:
    from ariadne.cli import main

    (tmp_path / "note.md").write_text("Halberd is co-located at Compound-Alpha.", encoding="utf-8")
    query = (
        "MATCH (:Person {name:'Halberd'})-[:MEMBER_OF]->(:Unit)"
        "-[:CO_LOCATED]->(:Site {name:'Compound-Alpha'})"
    )
    (tmp_path / "provenance.jsonl").write_text(json.dumps(_entry(query)) + "\n", encoding="utf-8")
    # eval scores existing artifacts — no ANTHROPIC_API_KEY needed
    assert main(["eval", str(tmp_path)]) == 0


def test_trajectory_reads_sql_statements_not_just_cypher_query() -> None:
    # A relational needle's statement lands under `sql`, not `query`; trajectory
    # scoring must see it or every SQL workup scores trajectory 0.
    note = "Halberd and Wren both front for Meridian Freight Ltd."
    entries = [_sql_entry("SELECT alias, cover_employer FROM personnel WHERE alias='H1'")]
    report = score_workup(note, entries, WREN_TIE_FIXTURE)
    assert report.trajectory == 1.0


def test_cross_store_tie_is_grounded_when_relational_queried_and_surfaced() -> None:
    note = "Halberd shares the cover employer Meridian Freight Ltd with Wren."
    entries = [
        _entry("MATCH (p:Person {name:'Halberd'}) RETURN p.alias"),
        _sql_entry("SELECT name, cover_employer FROM personnel"),
    ]
    report = score_workup(note, entries, WREN_TIE_FIXTURE)
    assert report.recall == 1.0
    assert report.trajectory == 1.0
    assert report.grounded is True


def test_naming_the_employer_tie_without_querying_relational_is_a_guess() -> None:
    # The note asserts the cross-modality tie but the agent only touched the graph
    # — the graph has no cover_employer, so this is a fabrication, not evidence.
    note = "Halberd shares the cover employer Meridian Freight Ltd with Wren."
    entries = [_entry("MATCH (p:Person {name:'Halberd'})-[:MEMBER_OF]->(u) RETURN u")]
    report = score_workup(note, entries, WREN_TIE_FIXTURE)
    assert report.recall == 1.0
    assert report.trajectory < 1.0
    assert report.grounded is False


def test_supporting_fact_f1_is_none_when_fixture_defines_no_facts() -> None:
    # The single-store HALBERD path scores; cross-edge F1 is opt-in per fixture.
    report = score_workup("anything", [_entry("q")], _fixture_with_facts())
    assert report.supporting_fact_f1 is None
    assert report.supporting_fact_precision is None
    assert report.supporting_fact_recall is None


def test_supporting_fact_recall_is_grounded_gold_edges_over_all_gold() -> None:
    # Two gold edges; the note surfaces both and the ledger traverses both.
    fixture = _fixture_with_facts(
        SupportingFact(note_markers=("Signals",), ledger_markers=("MEMBER_OF",)),
        SupportingFact(note_markers=("Compound-Alpha",), ledger_markers=("CO_LOCATED",)),
    )
    note = "Halberd is in Signals-Cell, co-located at Compound-Alpha."
    entries = [_entry("MATCH (:Person)-[:MEMBER_OF]->(:Unit)-[:CO_LOCATED]->(:Site)")]
    report = score_workup(note, entries, fixture)
    assert report.supporting_fact_recall == 1.0
    assert report.supporting_fact_precision == 1.0
    assert report.supporting_fact_f1 == 1.0


def test_supporting_fact_precision_drops_when_a_surfaced_edge_was_not_traversed() -> None:
    # The note asserts both edges (both surfaced) but the ledger only walked one —
    # the second is an ungrounded assertion, so precision falls to 1/2.
    fixture = _fixture_with_facts(
        SupportingFact(note_markers=("Signals",), ledger_markers=("MEMBER_OF",)),
        SupportingFact(note_markers=("Compound-Alpha",), ledger_markers=("CO_LOCATED",)),
    )
    note = "Halberd is in Signals-Cell, co-located at Compound-Alpha."
    entries = [_entry("MATCH (:Person)-[:MEMBER_OF]->(:Unit)")]  # never walked CO_LOCATED
    report = score_workup(note, entries, fixture)
    assert report.supporting_fact_recall == 0.5  # 1 of 2 gold edges grounded
    assert report.supporting_fact_precision == 0.5  # 1 of 2 surfaced edges grounded
    assert report.supporting_fact_f1 == 0.5


def test_supporting_fact_precision_is_grounded_over_surfaced_not_gold() -> None:
    # One gold edge. The note surfaces it but never traverses it (guess) → 0
    # grounded. Precision = 0/1 surfaced, recall = 0/1 gold.
    fixture = _fixture_with_facts(
        SupportingFact(note_markers=("Compound-Alpha",), ledger_markers=("CO_LOCATED",)),
    )
    report = score_workup("co-located at Compound-Alpha", [_entry("MATCH (p) RETURN p")], fixture)
    assert report.supporting_fact_precision == 0.0
    assert report.supporting_fact_recall == 0.0
    assert report.supporting_fact_f1 == 0.0


def test_halberd_fixture_carries_per_edge_supporting_facts() -> None:
    # The canonical single-store needle now scores per-edge F1: a grounded workup
    # that surfaces and traverses every bridge edge scores F1 = 1.0.
    note = (
        "Halberd is a member of the Signals-Cell, which is co-located at "
        "Compound-Alpha with the Logistics-Cell."
    )
    entries = [
        _entry("MATCH (:Person {name:'Halberd'})-[:MEMBER_OF]->(:Unit)-[:CO_LOCATED]->(:Site)"),
    ]
    report = score_workup(note, entries, HALBERD_FIXTURE)
    assert HALBERD_FIXTURE.supporting_facts  # non-empty
    assert report.supporting_fact_f1 == 1.0


def test_wren_tie_fixture_carries_per_edge_supporting_facts() -> None:
    note = "Halberd and Wren both front for Meridian Freight Ltd."
    entries = [_sql_entry("SELECT name, cover_employer FROM personnel")]
    report = score_workup(note, entries, WREN_TIE_FIXTURE)
    assert WREN_TIE_FIXTURE.supporting_facts
    assert report.supporting_fact_f1 == 1.0


def test_eval_subcommand_scores_cross_store_fixture(tmp_path) -> None:
    from ariadne.cli import main

    (tmp_path / "note.md").write_text(
        "Halberd shares cover employer Meridian Freight Ltd with Wren.", encoding="utf-8"
    )
    (tmp_path / "provenance.jsonl").write_text(
        json.dumps(_sql_entry("SELECT name, cover_employer FROM personnel")) + "\n",
        encoding="utf-8",
    )
    assert main(["eval", str(tmp_path), "--fixture", "wren-tie"]) == 0


def test_score_workup_dir_reads_note_and_provenance(tmp_path) -> None:
    (tmp_path / "note.md").write_text("Halberd is co-located at Compound-Alpha.", encoding="utf-8")
    query = (
        "MATCH (:Person {name:'Halberd'})-[:MEMBER_OF]->(:Unit)"
        "-[:CO_LOCATED]->(:Site {name:'Compound-Alpha'})"
    )
    (tmp_path / "provenance.jsonl").write_text(json.dumps(_entry(query)) + "\n", encoding="utf-8")
    report = score_workup_dir(tmp_path, HALBERD_FIXTURE)
    assert report.grounded is True
    assert report.queries_run == 1
