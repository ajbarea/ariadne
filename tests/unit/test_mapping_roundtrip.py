"""The propose -> freeze -> apply loop end to end (hermetic; ADR-0020 first slice)."""

from __future__ import annotations

from ariadne.datasets.canonical import Entity, Relationship
from ariadne.introspect.postgres import build_schema_summary
from ariadne.mapping.adapter import MappingDrivenAdapter
from ariadne.mapping.propose import baseline_mapping
from ariadne.mapping.schema import dump_mapping_toml, load_mapping_toml, validate_mapping

_COLUMNS = [
    {"table_name": "employees", "column_name": "id", "data_type": "integer"},
    {"table_name": "employees", "column_name": "name", "data_type": "text"},
    {"table_name": "employees", "column_name": "dept_id", "data_type": "integer"},
    {"table_name": "departments", "column_name": "id", "data_type": "integer"},
    {"table_name": "departments", "column_name": "name", "data_type": "text"},
]
_FKS = [
    {
        "from_table": "employees",
        "from_column": "dept_id",
        "to_table": "departments",
        "to_column": "id",
    }
]
_ROWS = {
    "employees": [{"id": 1, "name": "Halberd", "dept_id": 10}],
    "departments": [{"id": 10, "name": "Signals"}],
}


def test_introspect_propose_freeze_apply_round_trip() -> None:
    # introspect -> propose
    summary = build_schema_summary(_COLUMNS, _FKS)
    proposed = baseline_mapping(summary)
    # validate (the ratify gate) passes
    assert validate_mapping(proposed, summary) == []
    # freeze: serialize to TOML and read it back unchanged (what a human would edit)
    frozen = load_mapping_toml(dump_mapping_toml(proposed))
    assert frozen == proposed
    # apply: drive the canonical adapter over the user's rows
    out = list(
        MappingDrivenAdapter(name="acme", mapping=frozen, read_rows=_ROWS.__getitem__).load()
    )
    entity_ids = {c.id for c in out if isinstance(c, Entity)}
    rels = [c for c in out if isinstance(c, Relationship)]
    # baseline singularizes the table name into the entity type
    assert entity_ids == {"employee:1", "department:10"}
    assert len(rels) == 1
    assert (rels[0].src, rels[0].dst) == ("employee:1", "department:10")
