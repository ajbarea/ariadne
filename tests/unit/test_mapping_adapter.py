from __future__ import annotations

from ariadne.datasets.base import DatasetAdapter
from ariadne.datasets.canonical import Entity, Relationship
from ariadne.mapping.adapter import MappingDrivenAdapter
from ariadne.mapping.schema import EntityMapping, Mapping, RelationshipMapping

_MAPPING = Mapping(
    entities=(
        EntityMapping(
            table="employees",
            type="person",
            id_column="id",
            name_column="name",
            attribute_columns=("salary",),
        ),
        EntityMapping(table="departments", type="org", id_column="id", name_column="name"),
    ),
    relationships=(
        RelationshipMapping(
            type="MEMBER_OF",
            from_table="employees",
            to_table="departments",
            from_column="dept_id",
            to_column="id",
        ),
    ),
)

_ROWS = {
    "employees": [{"id": 1, "name": "Halberd", "dept_id": 10, "salary": 90}],
    "departments": [{"id": 10, "name": "Signals"}],
}


def _reader(table: str) -> list[dict]:
    return _ROWS[table]


def test_adapter_yields_entities_with_attributes_and_canonical_ids() -> None:
    out = list(MappingDrivenAdapter(name="acme", mapping=_MAPPING, read_rows=_reader).load())
    halberd = next(c for c in out if isinstance(c, Entity) and c.name == "Halberd")
    assert halberd.id == "person:1"
    assert halberd.type == "person"
    # dept_id is a relationship (excluded); only salary is an attribute, stringified
    assert halberd.attributes == {"salary": "90"}


def test_adapter_yields_relationships_from_foreign_keys() -> None:
    out = list(MappingDrivenAdapter(name="acme", mapping=_MAPPING, read_rows=_reader).load())
    rels = [c for c in out if isinstance(c, Relationship)]
    assert len(rels) == 1
    assert (rels[0].src, rels[0].type, rels[0].dst) == ("person:1", "MEMBER_OF", "org:10")


def test_adapter_satisfies_the_dataset_adapter_protocol() -> None:
    a = MappingDrivenAdapter(name="acme", mapping=_MAPPING, read_rows=_reader)
    assert isinstance(a, DatasetAdapter)
    assert a.access == "restricted"  # user data is read-only/restricted by default
    assert a.eval_fixtures() == []
