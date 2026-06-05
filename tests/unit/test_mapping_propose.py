from __future__ import annotations

from ariadne.introspect.postgres import Column, ForeignKey, SchemaSummary
from ariadne.mapping.propose import BaselineMapper, SchemaMapper, baseline_mapping
from ariadne.mapping.schema import Mapping, validate_mapping


def _summary() -> SchemaSummary:
    return SchemaSummary(
        tables={
            "employees": (
                Column("id", "integer"),
                Column("name", "text"),
                Column("dept_id", "integer"),
                Column("salary", "integer"),
            ),
            "departments": (Column("id", "integer"), Column("name", "text")),
        },
        foreign_keys=(ForeignKey("employees", "dept_id", "departments", "id"),),
    )


def test_baseline_maps_each_table_to_an_entity_with_id_name_and_singular_type() -> None:
    by_table = {e.table: e for e in baseline_mapping(_summary()).entities}
    assert set(by_table) == {"employees", "departments"}
    assert by_table["employees"].id_column == "id"
    assert by_table["employees"].name_column == "name"
    assert by_table["employees"].type == "employee"  # naive singularization


def test_baseline_excludes_id_name_and_fk_columns_from_attributes() -> None:
    emp = next(e for e in baseline_mapping(_summary()).entities if e.table == "employees")
    # dept_id is a foreign key (-> a relationship), id/name are surfaced separately;
    # only salary remains as a plain attribute.
    assert emp.attribute_columns == ("salary",)


def test_baseline_maps_each_foreign_key_to_a_relationship() -> None:
    rels = baseline_mapping(_summary()).relationships
    assert len(rels) == 1
    r = rels[0]
    assert (r.from_table, r.from_column, r.to_table, r.to_column) == (
        "employees",
        "dept_id",
        "departments",
        "id",
    )


def test_baseline_proposal_validates_against_its_own_summary() -> None:
    s = _summary()
    assert validate_mapping(baseline_mapping(s), s) == []


def test_baseline_mapper_satisfies_the_schema_mapper_protocol() -> None:
    mapper: SchemaMapper = BaselineMapper()
    assert isinstance(mapper, SchemaMapper)
    assert isinstance(mapper.propose(_summary()), Mapping)
