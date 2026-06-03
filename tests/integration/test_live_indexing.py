"""Live indexing: SyntheticAdapter canonical -> Neo4j; query the planted bridge."""

from __future__ import annotations

import pytest

pytest.importorskip("testcontainers")

from neo4j import GraphDatabase

from ariadne.datasets.load import load_graph
from ariadne.datasets.synthetic import SyntheticAdapter

pytestmark = pytest.mark.integration


def test_load_graph_reproduces_the_colocation_bridge(neo4j_conn) -> None:
    driver = GraphDatabase.driver(
        neo4j_conn["uri"], auth=(neo4j_conn["username"], neo4j_conn["password"])
    )
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")  # clean slate (fixture pre-seeds)
    load_graph(list(SyntheticAdapter().load()), driver)
    with driver.session() as s:
        rec = s.run(
            "MATCH (h:Person {id:'person:Halberd'})-[:MEMBER_OF]->(:Unit)"
            "-[:CO_LOCATED]->(site:Site)<-[:CO_LOCATED]-(:Unit)<-[:MEMBER_OF]-"
            "(w:Person {id:'person:Wren'}) RETURN site.name AS site"
        ).single()
    driver.close()
    assert rec is not None and rec["site"] == "Compound-Alpha"
