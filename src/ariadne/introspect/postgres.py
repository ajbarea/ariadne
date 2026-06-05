"""Read-only Postgres schema introspection (ADR-0020, axis A1).

Reads the SQL-standard ``information_schema`` views (portable + stable across
versions, unlike ``pg_catalog``) to produce a structured ``SchemaSummary`` the
schema-mapper can reason over. ``build_schema_summary`` is the pure, testable core;
``introspect`` runs the two read-only queries against a live connection.

# research(2026-06): information_schema (SQL-standard, read-only views) over
# pg_catalog for a generic, portable introspector — postgresql.org docs ch.35.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str


@dataclass(frozen=True)
class ForeignKey:
    from_table: str
    from_column: str
    to_table: str
    to_column: str


@dataclass(frozen=True)
class SchemaSummary:
    """A store's user-facing tables, their columns, and foreign keys."""

    tables: dict[str, tuple[Column, ...]]
    foreign_keys: tuple[ForeignKey, ...]


def build_schema_summary(column_rows: Iterable[dict], fk_rows: Iterable[dict]) -> SchemaSummary:
    """Group ``information_schema``-shaped rows into a ``SchemaSummary``.

    ``column_rows`` carry ``table_name`` / ``column_name`` / ``data_type`` (already
    ordered by ``ordinal_position``); ``fk_rows`` carry ``from_table`` /
    ``from_column`` / ``to_table`` / ``to_column``.
    """
    tables: dict[str, list[Column]] = {}
    for r in column_rows:
        tables.setdefault(r["table_name"], []).append(Column(r["column_name"], r["data_type"]))
    fks = tuple(
        ForeignKey(r["from_table"], r["from_column"], r["to_table"], r["to_column"])
        for r in fk_rows
    )
    return SchemaSummary(tables={t: tuple(cols) for t, cols in tables.items()}, foreign_keys=fks)


_COLUMNS_SQL = (
    "SELECT table_name, column_name, data_type "
    "FROM information_schema.columns "
    "WHERE table_schema = %s "
    "ORDER BY table_name, ordinal_position"
)
# Standard FK discovery: table_constraints -> key_column_usage (the referencing
# column) -> constraint_column_usage (the referenced column).
_FKS_SQL = (
    "SELECT tc.table_name AS from_table, kcu.column_name AS from_column, "
    "       ccu.table_name AS to_table, ccu.column_name AS to_column "
    "FROM information_schema.table_constraints tc "
    "JOIN information_schema.key_column_usage kcu "
    "  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
    "JOIN information_schema.constraint_column_usage ccu "
    "  ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema "
    "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = %s"
)


def introspect(conn: Any, schema: str = "public") -> SchemaSummary:
    """Introspect a live (read-only) Postgres connection's ``schema``.

    Issues only ``SELECT``s against ``information_schema``. The pure mapping lives in
    ``build_schema_summary``; this is the thin live-I/O shell (integration-tested).
    """
    with conn.cursor() as cur:
        cur.execute(_COLUMNS_SQL, (schema,))
        col_cols = [d[0] for d in cur.description]
        column_rows = [dict(zip(col_cols, row, strict=True)) for row in cur.fetchall()]
        cur.execute(_FKS_SQL, (schema,))
        fk_cols = [d[0] for d in cur.description]
        fk_rows = [dict(zip(fk_cols, row, strict=True)) for row in cur.fetchall()]
    return build_schema_summary(column_rows, fk_rows)


def postgres_row_reader(conn: Any, schema: str = "public") -> Any:
    """Return a ``RowReader`` (table name -> list of dict rows) over ``conn``.

    Read-only ``SELECT *`` per table; identifiers are quoted via ``psycopg.sql`` so a
    table name from introspection is interpolated safely. Used by
    ``MappingDrivenAdapter`` to project a user's Postgres onto the canonical schema.
    """
    from psycopg import sql

    def read(table: str) -> list[dict]:
        query = sql.SQL("SELECT * FROM {}.{}").format(sql.Identifier(schema), sql.Identifier(table))
        with conn.cursor() as cur:
            cur.execute(query)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]

    return read
