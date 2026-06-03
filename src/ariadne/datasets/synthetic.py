"""The synthetic org-graph dataset as the first adapter.

Mirrors infra/neo4j/seed.cypher so today's behaviour flows through the new
adapter seam. No external data; access is public.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from ariadne.datasets.base import register
from ariadne.datasets.canonical import Canonical, Entity, Relationship
from ariadne.evaluation.needle import HALBERD_FIXTURE, WREN_TIE_FIXTURE, NeedleFixture

if TYPE_CHECKING:
    from collections.abc import Iterable

_UNITS = [
    ("Directorate-HQ", {"echelon": "1"}),
    ("Operations-Wing", {"echelon": "2"}),
    ("Signals-Cell", {"echelon": "3"}),
    ("Logistics-Cell", {"echelon": "3"}),
]
_PERSONS = [("Halberd", "H1"), ("Wren", "W4"), ("Talon", "T2"), ("Osprey", "O7")]
_RELS = [
    ("unit:Operations-Wing", "unit:Directorate-HQ", "REPORTS_TO", {}),
    ("unit:Signals-Cell", "unit:Operations-Wing", "REPORTS_TO", {}),
    ("unit:Logistics-Cell", "unit:Operations-Wing", "REPORTS_TO", {}),
    ("person:Halberd", "unit:Signals-Cell", "MEMBER_OF", {"role": "Lead"}),
    ("person:Talon", "unit:Signals-Cell", "MEMBER_OF", {"role": "Analyst"}),
    ("person:Wren", "unit:Logistics-Cell", "MEMBER_OF", {"role": "Lead"}),
    ("person:Osprey", "unit:Logistics-Cell", "MEMBER_OF", {"role": "Driver"}),
    ("person:Halberd", "person:Talon", "COMMUNICATES_WITH", {"channel": "voice"}),
    ("unit:Signals-Cell", "site:Compound-Alpha", "CO_LOCATED", {}),
    ("unit:Logistics-Cell", "site:Compound-Alpha", "CO_LOCATED", {}),
]


class SyntheticAdapter:
    name: str = "synthetic"
    entity_type: str = "person"
    access: Literal["public", "restricted"] = "public"

    def load(self) -> Iterable[Canonical]:
        for name, attrs in _UNITS:
            yield Entity(id=f"unit:{name}", type="unit", name=name, attributes=attrs)
        yield Entity(id="site:Compound-Alpha", type="site", name="Compound-Alpha")
        for name, alias in _PERSONS:
            yield Entity(
                id=f"person:{name}",
                type="person",
                name=name,
                aliases=(alias,),
                attributes={"alias": alias},
            )
        for src, dst, rtype, attrs in _RELS:
            yield Relationship(src=src, dst=dst, type=rtype, attributes=attrs)

    def eval_fixtures(self) -> list[NeedleFixture]:
        return [HALBERD_FIXTURE, WREN_TIE_FIXTURE]


register(SyntheticAdapter())
