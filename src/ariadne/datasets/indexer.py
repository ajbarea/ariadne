"""Canonical records -> store-load statements.

Pure transform (no DB connection), so it is fully unit-testable; Phase B wires
its output to live stores during ingestion. Phase A covers the graph
(Entity/Relationship); Document/Attribute store-loading lands in Phase B.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ariadne.datasets.canonical import Canonical, Entity, Relationship

if TYPE_CHECKING:
    from collections.abc import Iterable


def label(entity_type: str) -> str:
    # "person" -> "Person"; matches the existing seed's typed labels.
    return entity_type[:1].upper() + entity_type[1:]


def _props(attributes: dict[str, str], alias: str = "n") -> str:
    # Deterministic, sorted; values are synthetic/fictional in Phase A.
    return ", ".join(f"{alias}.{k} = {v!r}" for k, v in sorted(attributes.items()))


def index_graph(records: Iterable[Canonical]) -> list[str]:
    """Return idempotent Cypher (MERGE) for Entity/Relationship records only."""
    out: list[str] = []
    for rec in records:
        if isinstance(rec, Entity):
            stmt = f"MERGE (n:{label(rec.type)} {{id: {rec.id!r}}}) SET n.name = {rec.name!r}"
            if rec.attributes:
                stmt += ", " + _props(rec.attributes, "n")
            out.append(stmt)
        elif isinstance(rec, Relationship):
            stmt = (
                f"MATCH (a {{id: {rec.src!r}}}), (b {{id: {rec.dst!r}}}) "
                f"MERGE (a)-[r:{rec.type}]->(b)"
            )
            if rec.attributes:
                stmt += " SET " + _props(rec.attributes, "r")
            out.append(stmt)
        # Document / Attribute: Phase B.
    return out
