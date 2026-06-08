from __future__ import annotations

from ariadne.datasets.canonical import Entity, Relationship
from ariadne.datasets.indexer import index_graph


def test_entity_becomes_idempotent_merge_keyed_on_id() -> None:
    cy = index_graph(
        [Entity(id="person:Halberd", type="person", name="Halberd", attributes={"alias": "H1"})]
    )
    assert any("MERGE" in s and "person:Halberd" in s for s in cy)
    assert any(":Person" in s for s in cy)  # type -> title-case label
    assert all("CREATE " not in s for s in cy)  # idempotent, not CREATE
    assert "alias" in cy[0] and "H1" in cy[0]


def test_entity_aliases_persist_as_a_list_property() -> None:
    # The canonical Entity carries `aliases` for resolution (ADR-0016); the indexer
    # must write them to the graph so the subgraph resolver's `n.aliases` clause is
    # live (and so the property key exists — no Neo4j "key does not exist" warning).
    cy = index_graph(
        [Entity(id="person:Ruth", type="person", name="Babe Ruth", aliases=("ruthba01", "George"))]
    )
    stmt = cy[0]
    assert "n.aliases = [" in stmt
    assert "'ruthba01'" in stmt and "'George'" in stmt


def test_entity_without_aliases_omits_the_property() -> None:
    # No empty list written when there are no aliases — keeps the MERGE clean.
    cy = index_graph([Entity(id="person:X", type="person", name="X")])
    assert "aliases" not in cy[0]


def test_relationship_matches_endpoints_by_id_then_merges_edge() -> None:
    cy = index_graph(
        [
            Relationship(
                src="person:Halberd",
                dst="unit:Signals-Cell",
                type="MEMBER_OF",
                attributes={"role": "Lead"},
            )
        ]
    )
    joined = "\n".join(cy)
    assert "person:Halberd" in joined and "unit:Signals-Cell" in joined
    assert "MERGE" in joined and "MEMBER_OF" in joined


def test_documents_and_attributes_are_skipped_in_phase_a() -> None:
    from ariadne.datasets.canonical import Attribute, Document

    cy = index_graph(
        [
            Document(id="d1", text="x"),
            Attribute(entity_id="person:X", key="k", value="v"),
        ]
    )
    assert cy == []
