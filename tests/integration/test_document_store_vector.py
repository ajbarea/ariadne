"""pgvector column + nearest-neighbour query (gated; needs Docker/Colima)."""

from __future__ import annotations

import pytest

pytest.importorskip("testcontainers")
pytest.importorskip("psycopg")

import psycopg
from testcontainers.postgres import PostgresContainer

from ariadne.datasets.canonical import Document
from ariadne.unstructured.document_store import (
    _vector_literal,
    ensure_schema,
    ensure_vector_schema,
    store_embeddings,
    upsert_documents,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def pg_conn():
    with PostgresContainer("pgvector/pgvector:pg17") as pg:
        info = (
            f"host={pg.get_container_host_ip()} port={pg.get_exposed_port(5432)} "
            f"user={pg.username} password={pg.password} dbname={pg.dbname}"
        )
        with psycopg.connect(info, autocommit=True) as conn:
            ensure_schema(conn)
            ensure_vector_schema(conn, dim=4)
            yield conn


def test_nearest_neighbour_returns_the_closest_vector(pg_conn) -> None:
    upsert_documents(pg_conn, [Document(id="a", text="alpha"), Document(id="b", text="beta")])
    store_embeddings(pg_conn, {"a": [1.0, 0.0, 0.0, 0.0], "b": [0.0, 1.0, 0.0, 0.0]})
    q = _vector_literal([0.9, 0.1, 0.0, 0.0])
    row = pg_conn.execute(
        b"SELECT id FROM documents WHERE embedding IS NOT NULL "
        b"ORDER BY embedding <=> %(q)s::vector LIMIT 1",
        {"q": q},
    ).fetchone()
    assert row[0] == "a"
