"""Seeded-Postgres integration coverage for the relational connector's store.

Proves the synthetic personnel seed loads and carries the planted cross-modality
link (Halberd & Wren share a cover employer). Gated like the Neo4j seed test —
needs a Docker daemon (Colima); skipped when testcontainers/psycopg are absent.
"""

from __future__ import annotations

import pathlib
import re

import pytest

pytest.importorskip("testcontainers")
pytest.importorskip("psycopg")

import psycopg
from testcontainers.postgres import PostgresContainer

SEED = pathlib.Path("infra/postgres/seed.sql")
pytestmark = pytest.mark.integration


def _statements(sql: str) -> list[str]:
    # strip -- comments (inline and full-line) first so a ';' inside a comment
    # cannot split a statement, then split on the remaining statement separators.
    no_comments = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in no_comments.split(";") if s.strip()]


@pytest.fixture(scope="module")
def pg_conn():
    with PostgresContainer("postgres:17") as pg:
        conninfo = (
            f"host={pg.get_container_host_ip()} port={pg.get_exposed_port(5432)} "
            f"user={pg.username} password={pg.password} dbname={pg.dbname}"
        )
        with psycopg.connect(conninfo, autocommit=True) as conn:
            for stmt in _statements(SEED.read_text()):
                conn.execute(stmt.encode())
            yield conn


def test_seed_has_planted_cross_modality_link(pg_conn) -> None:
    rows = pg_conn.execute(
        "SELECT name FROM personnel WHERE cover_employer = 'Meridian Freight Ltd' ORDER BY name"
    ).fetchall()
    assert [r[0] for r in rows] == ["Halberd", "Wren"]


def test_personnel_aliases_match_graph_person_aliases(pg_conn) -> None:
    # alias is the cross-store join key to the Neo4j Person.alias values.
    rows = pg_conn.execute("SELECT alias FROM personnel ORDER BY alias").fetchall()
    assert [r[0] for r in rows] == ["H1", "O7", "T2", "W4"]
