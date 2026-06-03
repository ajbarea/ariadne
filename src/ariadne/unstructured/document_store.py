"""Postgres document store — the full-text (lexical) retrieval leg.

A generated ``tsvector`` column + GIN index gives dependency-free full-text
search via ``websearch_to_tsquery``; the agent queries it through the existing
``postgres-mcp`` ``execute_sql`` tool. The semantic (pgvector) leg is a later
sub-phase. See ADR-0007.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ariadne.datasets.canonical import Attribute, Canonical, Document

if TYPE_CHECKING:
    from collections.abc import Iterable

SCHEMA_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS documents (
        id        TEXT PRIMARY KEY,
        text      TEXT NOT NULL,
        modality  TEXT NOT NULL DEFAULT 'text',
        metadata  JSONB NOT NULL DEFAULT '{}'::jsonb,
        sources   TEXT[] NOT NULL DEFAULT '{}',
        content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
    )
    """,
    "CREATE INDEX IF NOT EXISTS documents_tsv_gin ON documents USING gin (content_tsv)",
    """
    CREATE TABLE IF NOT EXISTS entity_attributes (
        entity_id TEXT NOT NULL,
        key       TEXT NOT NULL,
        value     TEXT NOT NULL,
        PRIMARY KEY (entity_id, key)
    )
    """,
)

_UPSERT_DOC = (
    "INSERT INTO documents (id, text, modality, metadata, sources) "
    "VALUES (%(id)s, %(text)s, %(modality)s, %(metadata)s::jsonb, %(sources)s) "
    "ON CONFLICT (id) DO UPDATE SET text = EXCLUDED.text, modality = EXCLUDED.modality, "
    "metadata = EXCLUDED.metadata, sources = EXCLUDED.sources"
)
# research(2026-06): psycopg3 maps Python lists to TEXT[] natively — no explicit
# cast needed for sources. For JSONB, a raw Python str is sent as TEXT; without
# the ::jsonb cast Postgres rejects it with "column is of type jsonb but
# expression is of type text". Using %(metadata)s::jsonb is the lightest fix
# (no extra psycopg.types.json wrapping required). Alternative is
# psycopg.types.json.Json(rec.metadata) + drop json.dumps, but that adds an
# import from a non-public sub-module path. The ::jsonb cast wins on simplicity.
_UPSERT_ATTR = (
    "INSERT INTO entity_attributes (entity_id, key, value) "
    "VALUES (%(entity_id)s, %(key)s, %(value)s) "
    "ON CONFLICT (entity_id, key) DO UPDATE SET value = EXCLUDED.value"
)


def document_rows(records: Iterable[Canonical]) -> list[dict]:
    return [
        {
            "id": rec.id,
            "text": rec.text,
            "modality": rec.modality,
            "metadata": json.dumps(rec.metadata),
            "sources": list(rec.source_entity_ids),
        }
        for rec in records
        if isinstance(rec, Document)
    ]


def attribute_rows(records: Iterable[Canonical]) -> list[dict]:
    return [
        {"entity_id": r.entity_id, "key": r.key, "value": r.value}
        for r in records
        if isinstance(r, Attribute)
    ]


def full_text_sql() -> str:
    """Parameterised full-text query (``%(q)s`` = natural-language search string)."""
    return (
        "SELECT id, text, modality, metadata, "
        "ts_rank(content_tsv, websearch_to_tsquery('english', %(q)s)) AS rank "
        "FROM documents "
        "WHERE content_tsv @@ websearch_to_tsquery('english', %(q)s) "
        "ORDER BY rank DESC LIMIT %(limit)s"
    )


def ensure_schema(conn) -> None:  # type: ignore[type-arg]
    for stmt in SCHEMA_DDL:
        conn.execute(stmt.encode())


def upsert_documents(conn, records: Iterable[Canonical]) -> int:  # type: ignore[type-arg]
    rows = document_rows(records)
    for row in rows:
        conn.execute(_UPSERT_DOC.encode(), row)
    return len(rows)


def upsert_attributes(conn, records: Iterable[Canonical]) -> int:  # type: ignore[type-arg]
    rows = attribute_rows(records)
    for row in rows:
        conn.execute(_UPSERT_ATTR.encode(), row)
    return len(rows)
