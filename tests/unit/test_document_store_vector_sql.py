from __future__ import annotations

from ariadne.unstructured.document_store import store_embedding_sql, vector_ddl


def test_vector_ddl_creates_extension_column_and_hnsw_index() -> None:
    ddl = "\n".join(vector_ddl(dim=384))
    assert "CREATE EXTENSION IF NOT EXISTS vector" in ddl
    assert "vector(384)" in ddl
    assert "USING hnsw" in ddl and "vector_cosine_ops" in ddl


def test_store_embedding_sql_is_parameterised_upsert() -> None:
    sql = store_embedding_sql()
    assert "UPDATE documents SET embedding" in sql
    assert "%(embedding)s" in sql and "%(id)s" in sql
