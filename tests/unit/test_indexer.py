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
