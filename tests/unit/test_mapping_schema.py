from __future__ import annotations

from ariadne.introspect.postgres import Column, ForeignKey, SchemaSummary
from ariadne.mapping.schema import (
    EntityMapping,
    Mapping,
    RelationshipMapping,
    dump_mapping_toml,
    load_mapping_toml,
    validate_mapping,
)


def _summary() -> SchemaSummary:
    return SchemaSummary(
        tables={
            "employees": (
                Column("id", "integer"),
                Column("name", "text"),
                Column("dept_id", "integer"),
            ),
            "departments": (Column("id", "integer"), Column("name", "text")),
        },
        foreign_keys=(ForeignKey("employees", "dept_id", "departments", "id"),),
    )


def _valid() -> Mapping:
    return Mapping(
        entities=(
            EntityMapping(
                table="employees",
                type="person",
                id_column="id",
                name_column="name",
                attribute_columns=("dept_id",),
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


def test_valid_mapping_has_no_errors() -> None:
    assert validate_mapping(_valid(), _summary()) == []


def test_validate_flags_a_column_not_in_the_schema() -> None:
    m = Mapping(
        entities=(
            EntityMapping(table="employees", type="person", id_column="id", name_column="ghost"),
        )
    )
    assert any("ghost" in e for e in validate_mapping(m, _summary()))


def test_validate_flags_an_entity_table_not_in_the_schema() -> None:
    m = Mapping(
        entities=(EntityMapping(table="aliens", type="person", id_column="id", name_column="name"),)
    )
    assert any("aliens" in e for e in validate_mapping(m, _summary()))


def test_validate_flags_a_relationship_endpoint_table_not_mapped() -> None:
    # departments is not mapped to an entity -> the edge cannot load (loadability).
    m = Mapping(
        entities=(
            EntityMapping(table="employees", type="person", id_column="id", name_column="name"),
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
    errs = validate_mapping(m, _summary())
    assert any("departments" in e and "not mapped" in e for e in errs)


def test_mapping_round_trips_through_toml() -> None:
    m = _valid()
    assert load_mapping_toml(dump_mapping_toml(m)) == m
