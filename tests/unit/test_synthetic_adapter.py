from __future__ import annotations

import ariadne.datasets.synthetic  # noqa: F401  (import registers it)
from ariadne.datasets.base import get_adapter
from ariadne.datasets.canonical import Entity, Relationship
from ariadne.datasets.indexer import index_graph
from ariadne.datasets.synthetic import SyntheticAdapter


def test_adapter_metadata() -> None:
    a = SyntheticAdapter()
    assert a.name == "synthetic"
    assert a.entity_type == "person"
    assert a.access == "public"


def test_load_yields_the_planted_needle_entities_and_edges() -> None:
    recs = list(SyntheticAdapter().load())
    entities = {r.name for r in recs if isinstance(r, Entity)}
    assert {"Halberd", "Wren", "Signals-Cell", "Logistics-Cell", "Compound-Alpha"} <= entities
    rels = {(r.type) for r in recs if isinstance(r, Relationship)}
    assert {"MEMBER_OF", "CO_LOCATED"} <= rels


def test_indexing_load_emits_the_colocation_bridge() -> None:
    cy = "\n".join(index_graph(SyntheticAdapter().load()))
    assert "Compound-Alpha" in cy and "CO_LOCATED" in cy


def test_registered_in_the_registry_on_import() -> None:
    assert get_adapter("synthetic").name == "synthetic"


def test_eval_fixtures_are_the_known_needles() -> None:
    names = {f.entity for f in SyntheticAdapter().eval_fixtures()}
    assert "Halberd" in names
