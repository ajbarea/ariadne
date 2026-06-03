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


# ---------------------------------------------------------------------------
# Vector (pgvector) leg — B3.1
# ---------------------------------------------------------------------------


def vector_ddl(dim: int) -> tuple[str, ...]:
    """DDL to add the pgvector column + HNSW cosine index (idempotent)."""
    return (
        "CREATE EXTENSION IF NOT EXISTS vector",
        f"ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding vector({dim})",
        "CREATE INDEX IF NOT EXISTS documents_embedding_hnsw "
        "ON documents USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)",
    )


def store_embedding_sql() -> str:
    """Parameterised: write one document's embedding (%(embedding)s = '[...]' vector literal)."""
    return "UPDATE documents SET embedding = %(embedding)s::vector WHERE id = %(id)s"


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def ensure_vector_schema(conn, dim: int) -> None:  # type: ignore[type-arg]
    for stmt in vector_ddl(dim):
        conn.execute(stmt.encode())


def store_embeddings(conn, id_to_vec: dict[str, list[float]]) -> int:  # type: ignore[type-arg]
    sql = store_embedding_sql().encode()
    for doc_id, vec in id_to_vec.items():
        conn.execute(sql, {"id": doc_id, "embedding": _vector_literal(vec)})
    return len(id_to_vec)


# ---------------------------------------------------------------------------
# Hybrid RRF search — B3.1 Task 3
# ---------------------------------------------------------------------------


def hybrid_search_sql(candidates: int = 20) -> str:
    """RRF-fused full-text + vector search.

    Params: %(q)s natural-language query, %(qvec)s the query embedding as a
    '[...]' vector literal, %(k)s RRF smoothing (use 60), %(limit)s. Each leg
    contributes 1/(k+rank); ranks come from row_number() over each leg's
    ordering. (ADR-0007; RRF needs no score normalization.)
    """
    cand = str(int(candidates))
    fts = (
        "WITH fts AS ("
        "  SELECT id, row_number() OVER ("
        "    ORDER BY ts_rank(content_tsv, websearch_to_tsquery('english', %(q)s)) DESC) AS rank"
        "  FROM documents WHERE content_tsv @@ websearch_to_tsquery('english', %(q)s)"
        "  ORDER BY ts_rank(content_tsv, websearch_to_tsquery('english', %(q)s)) DESC"
        "  LIMIT " + cand + "), "
    )
    vec = (
        "vec AS ("
        "  SELECT id, row_number() OVER (ORDER BY embedding <=> %(qvec)s::vector) AS rank"
        "  FROM documents WHERE embedding IS NOT NULL"
        "  ORDER BY embedding <=> %(qvec)s::vector LIMIT " + cand + ") "
    )
    tail = (
        "SELECT id, "
        "  COALESCE(1.0 / (%(k)s + fts.rank), 0) + COALESCE(1.0 / (%(k)s + vec.rank), 0) AS rrf "
        "FROM fts FULL OUTER JOIN vec USING (id) "
        "ORDER BY rrf DESC LIMIT %(limit)s"
    )
    return fts + vec + tail


def hybrid_search(conn, query: str, embedder, *, k: int = 60, limit: int = 10) -> list[str]:  # type: ignore[type-arg]
    """Embed ``query`` and return RRF-fused document ids (full-text + vector)."""
    qvec = _vector_literal(embedder.embed([query])[0])
    rows = conn.execute(
        hybrid_search_sql().encode(),
        {"q": query, "qvec": qvec, "k": k, "limit": limit},
    ).fetchall()
    return [r[0] for r in rows]
