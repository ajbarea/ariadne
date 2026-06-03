from __future__ import annotations

import ariadne.datasets.enron  # noqa: F401  (registers the fixture)
from ariadne.datasets.enron import KAMINSKI_AOL_FIXTURE
from ariadne.evaluation.needle import FIXTURES, score_workup


def test_fixture_is_registered() -> None:
    assert "kaminski-aol" in FIXTURES


def test_cross_account_tie_scores_grounded() -> None:
    note = "Kaminski forwards work mail to a personal account, vkaminski@aol.com."
    ledger = [
        {
            "id": "g1",
            "tool": "mcp__neo4j__read_neo4j_cypher",
            "tool_input": {
                "query": "MATCH (:Person {name:'vince.kaminski@enron.com'})"
                "-[:EMAILED]->(p) RETURN p.name"
            },
            "response_excerpt": "vkaminski@aol.com",
        }
    ]
    report = score_workup(note, ledger, KAMINSKI_AOL_FIXTURE)
    assert report.grounded is True
    assert report.supporting_fact_f1 == 1.0


def test_guess_without_traversal_is_not_grounded() -> None:
    note = "Kaminski uses vkaminski@aol.com."  # surfaced...
    ledger = [
        {
            "id": "g1",
            "tool": "mcp__neo4j__read_neo4j_cypher",
            "tool_input": {"query": "MATCH (p:Person {name:'vince.kaminski@enron.com'}) RETURN p"},
            "response_excerpt": "...",
        }
    ]  # ...but never walked an EMAILED edge
    report = score_workup(note, ledger, KAMINSKI_AOL_FIXTURE)
    assert report.grounded is False
