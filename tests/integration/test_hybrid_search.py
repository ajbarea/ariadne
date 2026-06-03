"""Hybrid RRF search fuses full-text + vector (gated; pgvector image + fake embedder)."""

from __future__ import annotations

import pytest

pytest.importorskip("testcontainers")
pytest.importorskip("psycopg")

import psycopg
from testcontainers.postgres import PostgresContainer

from ariadne.datasets.canonical import Document
from ariadne.unstructured.document_store import (
    ensure_schema,
    ensure_vector_schema,
    hybrid_search,
    store_embeddings,
    upsert_documents,
)
from ariadne.unstructured.embed import FakeEmbedder

pytestmark = pytest.mark.integration


def test_hybrid_search_finds_a_doc_by_either_leg() -> None:
    emb = FakeEmbedder(dim=8)
    with PostgresContainer("pgvector/pgvector:pg17") as pg:
        info = (
            f"host={pg.get_container_host_ip()} port={pg.get_exposed_port(5432)} "
            f"user={pg.username} password={pg.password} dbname={pg.dbname}"
        )
        with psycopg.connect(info, autocommit=True) as conn:
            ensure_schema(conn)
            ensure_vector_schema(conn, dim=emb.dim)
            docs = [
                Document(id="a", text="the shipment leaves Compound-Alpha at dawn"),
                Document(id="b", text="quarterly budget review notes"),
            ]
            upsert_documents(conn, docs)
            store_embeddings(conn, {d.id: emb.embed([d.text])[0] for d in docs})
            ids = hybrid_search(conn, "Compound-Alpha shipment", emb, limit=5)
            assert "a" in ids and ids[0] == "a"
