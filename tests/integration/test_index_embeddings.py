"""Integration test: load_documents with embedder populates + vector-searchable rows."""

from __future__ import annotations

import pytest

pytest.importorskip("testcontainers")
pytest.importorskip("psycopg")

import psycopg
from testcontainers.postgres import PostgresContainer

from ariadne.datasets.canonical import Document
from ariadne.datasets.load import load_documents
from ariadne.unstructured.embed import FakeEmbedder

pytestmark = pytest.mark.integration


def test_load_documents_with_embedder_populates_searchable_vectors() -> None:
    emb = FakeEmbedder(dim=8)
    with PostgresContainer("pgvector/pgvector:pg17") as pg:
        info = (
            f"host={pg.get_container_host_ip()} port={pg.get_exposed_port(5432)} "
            f"user={pg.username} password={pg.password} dbname={pg.dbname}"
        )
        with psycopg.connect(info, autocommit=True) as conn:
            load_documents(
                [Document(id="a", text="alpha"), Document(id="b", text="beta")],
                conn,
                embedder=emb,
            )
            row = conn.execute(
                b"SELECT count(*) FROM documents WHERE embedding IS NOT NULL"
            ).fetchone()
            assert row is not None
            assert row[0] == 2
