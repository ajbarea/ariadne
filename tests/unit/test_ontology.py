"""The declarative user ontology (ADR-0027): load a TOML vocabulary + enforce it.

An ontology is a user's *closed* vocabulary — their entity types and the
relationship types that connect them (``domain -> range``). ``load_ontology_toml``
parses it; ``validate_against_ontology`` checks a proposed ``Mapping`` speaks only
that vocabulary and routes every edge the way the ontology declares.
"""

from __future__ import annotations

from ariadne.mapping.ontology import (
    Ontology,
    RelationshipType,
    load_ontology_toml,
    validate_against_ontology,
)
from ariadne.mapping.schema import EntityMapping, Mapping, RelationshipMapping

_ONTOLOGY_TOML = """
[[entity_types]]
name = "person"
description = "A named individual."

[[entity_types]]
name = "org"

[[relationship_types]]
name = "MEMBER_OF"
domain = "person"
range = "org"
description = "A person belongs to an organization."
"""


def _ontology() -> Ontology:
    return load_ontology_toml(_ONTOLOGY_TOML)


def _conformant_mapping() -> Mapping:
    return Mapping(
        entities=(
            EntityMapping("employees", "person", "id", "name", ("salary",)),
            EntityMapping("departments", "org", "id", "name"),
        ),
        relationships=(
            RelationshipMapping("MEMBER_OF", "employees", "departments", "dept_id", "id"),
        ),
    )


# ── load_ontology_toml: TOML vocabulary -> Ontology ──


def test_load_parses_entity_and_relationship_types() -> None:
    ont = _ontology()
    assert {e.name for e in ont.entity_types} == {"person", "org"}
    assert [r.name for r in ont.relationship_types] == ["MEMBER_OF"]


def test_load_carries_relationship_domain_and_range() -> None:
    member_of = _ontology().relationship_types[0]
    assert member_of.domain == "person"
    assert member_of.range == "org"


def test_load_defaults_missing_description_to_empty() -> None:
    org = next(e for e in _ontology().entity_types if e.name == "org")
    assert org.description == ""


# ── validate_against_ontology: the mapping speaks only the declared vocabulary ──


def test_conformant_mapping_has_no_errors() -> None:
    assert validate_against_ontology(_conformant_mapping(), _ontology()) == []


def test_rejects_an_entity_type_not_in_the_vocabulary() -> None:
    mapping = Mapping(entities=(EntityMapping("widgets", "gadget", "id", "name"),))
    errors = validate_against_ontology(mapping, _ontology())
    assert any("gadget" in e and "ontology" in e for e in errors)


def test_rejects_a_relationship_type_not_in_the_vocabulary() -> None:
    mapping = Mapping(
        entities=(
            EntityMapping("employees", "person", "id", "name"),
            EntityMapping("departments", "org", "id", "name"),
        ),
        relationships=(
            RelationshipMapping("REPORTS_TO", "employees", "departments", "dept_id", "id"),
        ),
    )
    errors = validate_against_ontology(mapping, _ontology())
    assert any("REPORTS_TO" in e for e in errors)


def test_rejects_a_relationship_whose_domain_does_not_match_the_routing() -> None:
    # MEMBER_OF is declared person -> org; here it runs org -> org (wrong domain).
    mapping = Mapping(
        entities=(
            EntityMapping("departments", "org", "id", "name"),
            EntityMapping("companies", "org", "id", "name"),
        ),
        relationships=(
            RelationshipMapping("MEMBER_OF", "departments", "companies", "co_id", "id"),
        ),
    )
    errors = validate_against_ontology(mapping, _ontology())
    assert any("MEMBER_OF" in e and "domain" in e and "person" in e for e in errors)


def test_rejects_a_relationship_whose_range_does_not_match_the_routing() -> None:
    # MEMBER_OF person -> org; here the to-side is a person, not an org (wrong range).
    mapping = Mapping(
        entities=(
            EntityMapping("employees", "person", "id", "name"),
            EntityMapping("managers", "person", "id", "name"),
        ),
        relationships=(RelationshipMapping("MEMBER_OF", "employees", "managers", "mgr_id", "id"),),
    )
    errors = validate_against_ontology(mapping, _ontology())
    assert any("MEMBER_OF" in e and "range" in e and "org" in e for e in errors)


def test_unmapped_endpoint_is_left_to_the_structural_validator() -> None:
    # from_table isn't an entity at all -> validate_mapping owns that error, not us;
    # we must not double-report a routing complaint we can't evaluate.
    mapping = Mapping(
        entities=(EntityMapping("departments", "org", "id", "name"),),
        relationships=(RelationshipMapping("MEMBER_OF", "ghost", "departments", "dept_id", "id"),),
    )
    errors = validate_against_ontology(mapping, _ontology())
    assert errors == []


def test_relationship_type_helpers_expose_names() -> None:
    ont = _ontology()
    assert ont.entity_type_names == frozenset({"person", "org"})
    assert ont.relationship_type_names == frozenset({"MEMBER_OF"})
    assert isinstance(ont.relationship_by_name["MEMBER_OF"], RelationshipType)
