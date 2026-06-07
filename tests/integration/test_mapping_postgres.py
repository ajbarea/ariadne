"""Live Postgres: the introspect -> propose -> validate -> apply loop (ADR-0020).

Gated by the ``integration`` marker; needs Docker/Colima. Creates a tiny two-table
schema with a foreign key, then drives the real `information_schema` introspection +
the mapping-driven adapter end to end.
"""

from __future__ import annotations

import pytest

pytest.importorskip("testcontainers")
pytest.importorskip("psycopg")

import os

import psycopg
from neo4j import GraphDatabase
from testcontainers.postgres import PostgresContainer

from ariadne.datasets.base import DATASETS, get_adapter
from ariadne.datasets.canonical import Entity, Relationship
from ariadne.datasets.load import load_graph
from ariadne.datasets.mapping_source import discover_and_register
from ariadne.introspect.postgres import introspect, postgres_row_reader
from ariadne.mapping.adapter import MappingDrivenAdapter
from ariadne.mapping.propose import baseline_mapping
from ariadne.mapping.schema import (
    DatasetHeader,
    EntityMapping,
    Mapping,
    RelationshipMapping,
    dump_mapping_toml,
    validate_mapping,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def pg_conn():
    """A seeded source Postgres: yields ``{"conn", "dsn"}`` (the DSN feeds the lazy reader)."""
    with PostgresContainer("postgres:17") as pg:
        info = (
            f"host={pg.get_container_host_ip()} port={pg.get_exposed_port(5432)} "
            f"user={pg.username} password={pg.password} dbname={pg.dbname}"
        )
        with psycopg.connect(info, autocommit=True) as conn:
            conn.execute("CREATE TABLE departments (id int PRIMARY KEY, name text)")
            conn.execute(
                "CREATE TABLE employees ("
                "id int PRIMARY KEY, name text, salary int, "
                "dept_id int REFERENCES departments(id))"
            )
            conn.execute("INSERT INTO departments VALUES (10,'Signals'),(20,'Logistics')")
            conn.execute("INSERT INTO employees VALUES (1,'Halberd',90,10),(2,'Wren',80,20)")
            yield {"conn": conn, "dsn": info}


def test_introspection_discovers_tables_columns_and_foreign_keys(pg_conn) -> None:
    summary = introspect(pg_conn["conn"], schema="public")
    assert {"employees", "departments"} <= set(summary.tables)
    emp_cols = {c.name for c in summary.tables["employees"]}
    assert {"id", "name", "salary", "dept_id"} <= emp_cols
    assert any(
        fk.from_table == "employees"
        and fk.from_column == "dept_id"
        and fk.to_table == "departments"
        for fk in summary.foreign_keys
    )


def test_propose_validate_apply_over_live_postgres(pg_conn) -> None:
    summary = introspect(pg_conn["conn"], schema="public")
    mapping = baseline_mapping(summary)
    assert validate_mapping(mapping, summary) == []
    adapter = MappingDrivenAdapter(
        name="acme", mapping=mapping, read_rows=postgres_row_reader(pg_conn["conn"])
    )
    out = list(adapter.load())
    entity_ids = {c.id for c in out if isinstance(c, Entity)}
    assert {"employee:1", "employee:2", "department:10", "department:20"} <= entity_ids
    rels = [c for c in out if isinstance(c, Relationship)]
    assert any(r.src == "employee:1" and r.dst == "department:10" for r in rels)
    # the salary attribute survives onto the entity
    halberd = next(c for c in out if isinstance(c, Entity) and c.name == "Halberd")
    assert halberd.attributes.get("salary") == "90"


def test_ratified_mapping_indexes_into_the_graph(
    pg_conn, neo4j_conn, tmp_path, monkeypatch
) -> None:
    """The full apply loop (ADR-0025): a ratified ``mapping.toml`` under
    ``ARIADNE_MAPPINGS`` is discovered as a dataset, its lazy reader opens the live
    source Postgres only at ``load()``, and the *existing* indexer loads it into Neo4j
    where the foreign key resolves to a typed, ``MATCH``-able edge."""
    # A human-ratified mapping (canonical types chosen by hand, not the baseline guess).
    mapping = Mapping(
        entities=(
            EntityMapping(
                table="employees",
                type="staff",
                id_column="id",
                name_column="name",
                attribute_columns=("salary",),
            ),
            EntityMapping(table="departments", type="dept", id_column="id", name_column="name"),
        ),
        relationships=(
            RelationshipMapping(
                type="WORKS_IN",
                from_table="employees",
                to_table="departments",
                from_column="dept_id",
                to_column="id",
            ),
        ),
    )
    (tmp_path / "acme.toml").write_text(
        dump_mapping_toml(mapping, header=DatasetHeader("acme", dsn_env="ARIADNE_SOURCE_DSN")),
        encoding="utf-8",
    )
    monkeypatch.setenv("ARIADNE_MAPPINGS", str(tmp_path))
    monkeypatch.setenv("ARIADNE_SOURCE_DSN", pg_conn["dsn"])

    driver = GraphDatabase.driver(
        neo4j_conn["uri"], auth=(neo4j_conn["username"], neo4j_conn["password"])
    )
    try:
        # discover -> register; the lazy reader connects to the source DB only here, at load()
        assert "acme" in discover_and_register(dict(os.environ))
        load_graph(list(get_adapter("acme").load()), driver)  # the EXISTING indexer, unchanged
        with driver.session() as session:
            row = session.run(
                "MATCH (s:Staff {name: 'Halberd'})-[:WORKS_IN]->(d:Dept) "
                "RETURN d.name AS dept, s.salary AS salary"
            ).single()
        assert row is not None  # the FK became a real, traversable edge
        assert row["dept"] == "Signals"
        assert row["salary"] == "90"  # the ratified attribute column survived ingest
    finally:
        with driver.session() as session:  # keep the shared session graph clean
            session.run("MATCH (n:Staff) DETACH DELETE n")
            session.run("MATCH (n:Dept) DETACH DELETE n")
        driver.close()
        DATASETS.pop("acme", None)
