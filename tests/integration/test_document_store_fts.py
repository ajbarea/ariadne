"""Full-text retrieval over the document store (gated; needs Docker/Colima)."""

from __future__ import annotations

import pytest

pytest.importorskip("testcontainers")
pytest.importorskip("psycopg")

import psycopg
from testcontainers.postgres import PostgresContainer

from ariadne.datasets.canonical import Document
from ariadne.unstructured.document_store import ensure_schema, full_text_sql, upsert_documents

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def pg_conn():
    with PostgresContainer("postgres:17") as pg:
        info = (
            f"host={pg.get_container_host_ip()} port={pg.get_exposed_port(5432)} "
            f"user={pg.username} password={pg.password} dbname={pg.dbname}"
        )
        with psycopg.connect(info, autocommit=True) as conn:
            ensure_schema(conn)
            yield conn


def test_full_text_finds_the_matching_document(pg_conn) -> None:
    upsert_documents(
        pg_conn,
        [
            Document(id="e1", text="The shipment leaves Compound-Alpha at dawn."),
            Document(id="e2", text="Budget review for the quarter, no logistics content."),
        ],
    )
    rows = pg_conn.execute(
        full_text_sql().encode(), {"q": "Compound-Alpha shipment", "limit": 5}
    ).fetchall()
    assert rows and rows[0][0] == "e1"


def test_upsert_is_idempotent(pg_conn) -> None:
    doc = Document(id="dup", text="repeated insert")
    upsert_documents(pg_conn, [doc])
    upsert_documents(pg_conn, [doc])
    n = pg_conn.execute(b"SELECT count(*) FROM documents WHERE id = 'dup'").fetchone()[0]
    assert n == 1
