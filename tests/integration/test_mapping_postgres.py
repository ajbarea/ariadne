"""Live Postgres: the introspect -> propose -> validate -> apply loop (ADR-0020).

Gated by the ``integration`` marker; needs Docker/Colima. Creates a tiny two-table
schema with a foreign key, then drives the real `information_schema` introspection +
the mapping-driven adapter end to end.
"""

from __future__ import annotations

import pytest

pytest.importorskip("testcontainers")
pytest.importorskip("psycopg")

import psycopg
from testcontainers.postgres import PostgresContainer

from ariadne.datasets.canonical import Entity, Relationship
from ariadne.introspect.postgres import introspect, postgres_row_reader
from ariadne.mapping.adapter import MappingDrivenAdapter
from ariadne.mapping.propose import baseline_mapping
from ariadne.mapping.schema import validate_mapping

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def pg_conn():
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
            yield conn


def test_introspection_discovers_tables_columns_and_foreign_keys(pg_conn) -> None:
    summary = introspect(pg_conn, schema="public")
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
    summary = introspect(pg_conn, schema="public")
    mapping = baseline_mapping(summary)
    assert validate_mapping(mapping, summary) == []
    adapter = MappingDrivenAdapter(
        name="acme", mapping=mapping, read_rows=postgres_row_reader(pg_conn)
    )
    out = list(adapter.load())
    entity_ids = {c.id for c in out if isinstance(c, Entity)}
    assert {"employee:1", "employee:2", "department:10", "department:20"} <= entity_ids
    rels = [c for c in out if isinstance(c, Relationship)]
    assert any(r.src == "employee:1" and r.dst == "department:10" for r in rels)
    # the salary attribute survives onto the entity
    halberd = next(c for c in out if isinstance(c, Entity) and c.name == "Halberd")
    assert halberd.attributes.get("salary") == "90"
