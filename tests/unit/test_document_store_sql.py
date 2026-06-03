from __future__ import annotations

from ariadne.datasets.canonical import Attribute, Document
from ariadne.unstructured.document_store import (
    SCHEMA_DDL,
    attribute_rows,
    document_rows,
    full_text_sql,
)


def test_schema_uses_generated_tsvector_and_gin() -> None:
    ddl = "\n".join(SCHEMA_DDL)
    assert "GENERATED ALWAYS AS" in ddl and "to_tsvector" in ddl
    assert "using gin" in ddl.lower()


def test_document_rows_map_canonical_fields() -> None:
    rows = document_rows(
        [
            Document(
                id="email:1",
                text="hello world",
                source_entity_ids=("person:X",),
                metadata={"subject": "hi"},
                modality="email_body",
            )
        ]
    )
    assert rows[0]["id"] == "email:1"
    assert rows[0]["text"] == "hello world"
    assert rows[0]["modality"] == "email_body"


def test_attribute_rows_map_canonical_fields() -> None:
    rows = attribute_rows([Attribute(entity_id="person:X", key="role", value="Lead")])
    assert rows[0] == {"entity_id": "person:X", "key": "role", "value": "Lead"}


def test_full_text_sql_uses_websearch_tsquery() -> None:
    sql = full_text_sql()
    assert "websearch_to_tsquery" in sql and "content_tsv" in sql and "%(q)s" in sql
