"""Execute canonical records into live stores.

Pure statement-building (``graph_statements``) stays unit-testable; the
``load_*`` functions run them against a driver/connection. Graph ingest is
idempotent via per-label id-uniqueness constraints + the MERGE statements from
``index_graph`` (ADR-0007 / best-practice MERGE-with-constraint).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ariadne.datasets.canonical import Canonical, Entity

if TYPE_CHECKING:
    from collections.abc import Iterable
from ariadne.datasets.indexer import index_graph, label
from ariadne.unstructured.document_store import (
    ensure_schema,
    upsert_attributes,
    upsert_documents,
)


def graph_statements(records: list[Canonical]) -> list[str]:
    """Constraints (one per distinct entity label) first, then MERGE statements."""
    labels = sorted({label(r.type) for r in records if isinstance(r, Entity)})
    constraints = [
        f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{lbl}) REQUIRE n.id IS UNIQUE" for lbl in labels
    ]
    return constraints + index_graph(records)


def load_graph(records: list[Canonical], driver) -> int:
    stmts = graph_statements(records)
    with driver.session() as session:
        for stmt in stmts:
            session.run(stmt)
    return len(stmts)


def load_documents(records: Iterable[Canonical], conn, embedder=None) -> tuple[int, int]:
    records = list(records)
    ensure_schema(conn)
    n_docs = upsert_documents(conn, records)
    n_attrs = upsert_attributes(conn, records)
    if embedder is not None:
        from ariadne.datasets.canonical import Document
        from ariadne.unstructured.document_store import ensure_vector_schema, store_embeddings

        docs = [r for r in records if isinstance(r, Document)]
        if docs:
            ensure_vector_schema(conn, embedder.dim)
            vecs = embedder.embed([d.text for d in docs])
            store_embeddings(conn, {d.id: v for d, v in zip(docs, vecs, strict=True)})
    return n_docs, n_attrs
