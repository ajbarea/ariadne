from __future__ import annotations

from ariadne.introspect.postgres import (
    Column,
    ForeignKey,
    build_schema_summary,
    introspect,
)


class _FakeCursor:
    """Minimal psycopg-cursor stand-in: serves queued (description, rows) per execute."""

    def __init__(self, results: list[tuple[list[str], list[tuple]]]) -> None:
        self._results = results
        self._i = -1
        self.description: list[tuple] = []
        self._rows: list[tuple] = []

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, _sql: str, _params: object) -> None:
        self._i += 1
        cols, self._rows = self._results[self._i]
        self.description = [(c,) for c in cols]

    def fetchall(self) -> list[tuple]:
        return self._rows


class _FakeConn:
    def __init__(self, results: list[tuple[list[str], list[tuple]]]) -> None:
        self._results = results

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._results)


def test_introspect_reads_columns_then_foreign_keys_off_a_connection() -> None:
    results = [
        (
            ["table_name", "column_name", "data_type"],
            [("employees", "id", "integer"), ("employees", "name", "text")],
        ),
        (
            ["from_table", "from_column", "to_table", "to_column"],
            [("employees", "mgr_id", "employees", "id")],
        ),
    ]
    s = introspect(_FakeConn(results), schema="public")
    assert s.tables["employees"] == (Column("id", "integer"), Column("name", "text"))
    assert s.foreign_keys == (ForeignKey("employees", "mgr_id", "employees", "id"),)


def test_build_schema_summary_groups_columns_by_table_in_order() -> None:
    cols = [
        {"table_name": "employees", "column_name": "id", "data_type": "integer"},
        {"table_name": "employees", "column_name": "name", "data_type": "text"},
        {"table_name": "employees", "column_name": "dept_id", "data_type": "integer"},
        {"table_name": "departments", "column_name": "id", "data_type": "integer"},
        {"table_name": "departments", "column_name": "name", "data_type": "text"},
    ]
    fks = [
        {
            "from_table": "employees",
            "from_column": "dept_id",
            "to_table": "departments",
            "to_column": "id",
        }
    ]
    s = build_schema_summary(cols, fks)
    assert set(s.tables) == {"employees", "departments"}
    assert s.tables["employees"] == (
        Column("id", "integer"),
        Column("name", "text"),
        Column("dept_id", "integer"),
    )
    assert s.foreign_keys == (ForeignKey("employees", "dept_id", "departments", "id"),)


def test_build_schema_summary_handles_a_table_with_no_foreign_keys() -> None:
    cols = [{"table_name": "lonely", "column_name": "id", "data_type": "uuid"}]
    s = build_schema_summary(cols, [])
    assert s.tables["lonely"] == (Column("id", "uuid"),)
    assert s.foreign_keys == ()
