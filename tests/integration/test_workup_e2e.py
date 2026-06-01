from __future__ import annotations

import json
import os

import pytest
from neo4j import GraphDatabase

from ariadne.cli import run_workup

pytestmark = pytest.mark.integration


def test_seed_has_planted_multihop_link(neo4j_conn) -> None:
    """Key-free: proves the testcontainers Neo4j + seed + driver path works."""
    driver = GraphDatabase.driver(
        neo4j_conn["uri"], auth=(neo4j_conn["username"], neo4j_conn["password"])
    )
    with driver.session() as session:
        row_n = session.run("MATCH (n) RETURN count(n) AS c").single()
        assert row_n is not None
        nodes = row_n["c"]
        row_p = session.run(
            "MATCH p=(:Person {name:'Halberd'})-[:MEMBER_OF]->(:Unit)-[:CO_LOCATED]->"
            "(:Site)<-[:CO_LOCATED]-(:Unit)<-[:MEMBER_OF]-(:Person {name:'Wren'}) "
            "RETURN count(p) AS c"
        ).single()
        assert row_p is not None
        path = row_p["c"]
    driver.close()
    assert nodes == 9
    assert path >= 1


@pytest.mark.asyncio
async def test_live_workup_produces_cited_note(neo4j_conn, tmp_path) -> None:
    """Key-gated: runs the real agent loop end-to-end."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("no ANTHROPIC_API_KEY — live agent run skipped")

    env = {
        **os.environ,
        "NEO4J_URI": neo4j_conn["uri"],
        "NEO4J_USERNAME": neo4j_conn["username"],
        "NEO4J_PASSWORD": neo4j_conn["password"],
    }
    rc = await run_workup("Halberd", str(tmp_path), env)

    out = tmp_path / "halberd"
    note = (out / "note.md").read_text()
    citations = json.loads((out / "citations.json").read_text())

    assert rc == 0
    assert citations["ok"] is True
    assert citations["cited"], "note must cite at least one graph call"
    assert (out / "provenance.jsonl").read_text().strip()
    # success criterion (4): surfaces the planted non-obvious link
    assert "Compound-Alpha" in note or "co-located" in note.lower()
