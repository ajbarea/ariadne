"""Hermetic tests: load_documents embed path issues vector DDL + upserts without a real DB."""

from __future__ import annotations

from ariadne.datasets.canonical import Document
from ariadne.datasets.load import load_documents
from ariadne.unstructured.embed import FakeEmbedder


class _Conn:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def execute(self, q, params=None):
        self.sql.append(q.decode() if isinstance(q, bytes) else str(q))
        return self

    def fetchall(self):
        return []


def test_load_documents_without_embedder_does_not_touch_vector_schema() -> None:
    conn = _Conn()
    load_documents([Document(id="d1", text="hello")], conn)
    joined = "\n".join(conn.sql)
    # pgvector-specific DDL must be absent; base schema uses tsvector (expected)
    assert "CREATE EXTENSION IF NOT EXISTS vector" not in joined
    assert "embedding vector(" not in joined
    assert "UPDATE documents SET embedding" not in joined


def test_load_documents_with_embedder_creates_vector_schema_and_stores() -> None:
    conn = _Conn()
    load_documents([Document(id="d1", text="hello world")], conn, embedder=FakeEmbedder(dim=8))
    joined = "\n".join(conn.sql)
    assert "CREATE EXTENSION IF NOT EXISTS vector" in joined
    assert "embedding vector(8)" in joined
    assert "UPDATE documents SET embedding" in joined
