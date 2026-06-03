from __future__ import annotations

from ariadne.unstructured.document_store import hybrid_search_sql


def test_hybrid_sql_fuses_fulltext_and_vector_with_rrf() -> None:
    sql = hybrid_search_sql()
    assert "websearch_to_tsquery" in sql  # full-text leg
    assert "<=>" in sql and "::vector" in sql  # vector leg
    assert "FULL OUTER JOIN" in sql  # union of both legs
    assert "1.0 / (%(k)s +" in sql  # RRF term
    assert "%(q)s" in sql and "%(qvec)s" in sql and "%(limit)s" in sql
