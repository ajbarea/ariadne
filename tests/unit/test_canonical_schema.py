from __future__ import annotations

from ariadne.datasets.canonical import (
    SCHEMA_VERSION,
    Attribute,
    Document,
    Entity,
    Relationship,
)


def test_entity_holds_identity_and_open_attributes() -> None:
    e = Entity(
        id="person:Halberd",
        type="person",
        name="Halberd",
        aliases=("H1",),
        attributes={"clearance": "SECRET"},
    )
    assert e.id == "person:Halberd"
    assert e.attributes["clearance"] == "SECRET"


def test_relationship_references_entity_ids() -> None:
    r = Relationship(
        src="person:Halberd", dst="unit:Signals-Cell", type="MEMBER_OF", attributes={"role": "Lead"}
    )
    assert r.src == "person:Halberd"
    assert r.type == "MEMBER_OF"


def test_document_carries_text_metadata_and_sources() -> None:
    d = Document(
        id="email:1",
        text="hello",
        source_entity_ids=("person:Halberd",),
        metadata={"subject": "hi"},
        modality="email_body",
    )
    assert d.modality == "email_body"
    assert "person:Halberd" in d.source_entity_ids


def test_attribute_is_a_per_entity_fact() -> None:
    a = Attribute(entity_id="person:Halberd", key="role", value="Signals Lead")
    assert a.entity_id == "person:Halberd"


def test_schema_version_is_set() -> None:
    assert isinstance(SCHEMA_VERSION, int) and SCHEMA_VERSION >= 1
