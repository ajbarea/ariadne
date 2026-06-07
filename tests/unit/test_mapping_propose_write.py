"""`propose_and_write` — the testable core of `ariadne map` (hermetic, fake conn)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ariadne.mapping.ontology import load_ontology_toml
from ariadne.mapping.propose import propose_and_write
from ariadne.mapping.schema import DatasetHeader, load_dataset_header, load_mapping_toml

if TYPE_CHECKING:
    from pathlib import Path


class _FakeCursor:
    def __init__(self, results: list[tuple[list[str], list[tuple]]]) -> None:
        self._results = results
        self._i = -1
        self.description: list[tuple] = []
        self._rows: list[tuple] = []

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, _sql: str, _params: object = None) -> None:
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


def test_propose_and_write_writes_a_valid_draft(tmp_path: Path) -> None:
    results = [
        (
            ["table_name", "column_name", "data_type"],
            [("people", "id", "integer"), ("people", "name", "text")],
        ),
        (["from_table", "from_column", "to_table", "to_column"], []),
    ]
    out = tmp_path / "mapping.toml"
    mapping, errors = propose_and_write(_FakeConn(results), out, schema="public")
    assert errors == []
    assert out.exists()
    # the draft round-trips back to the proposed mapping
    assert load_mapping_toml(out.read_text(encoding="utf-8")) == mapping
    assert mapping.entities[0].table == "people"


def test_propose_and_write_stamps_a_dataset_header_when_given_one(tmp_path: Path) -> None:
    results = [
        (["table_name", "column_name", "data_type"], [("people", "id", "integer")]),
        (["from_table", "from_column", "to_table", "to_column"], []),
    ]
    out = tmp_path / "mapping.toml"
    propose_and_write(
        _FakeConn(results), out, schema="public", header=DatasetHeader("acme", dsn_env="ACME_DSN")
    )
    # the draft is apply-able: it carries the [dataset] header a human ratifies
    assert load_dataset_header(out.read_text(encoding="utf-8")) == DatasetHeader(
        "acme", dsn_env="ACME_DSN"
    )


def test_propose_and_write_surfaces_ontology_violations(tmp_path: Path) -> None:
    # The baseline types `widgets` -> "widget" (singularized); an ontology of only
    # person/org rejects it, so the conformance error is surfaced alongside the
    # (clean) structural check — the draft is still written for the human to fix.
    results = [
        (
            ["table_name", "column_name", "data_type"],
            [("widgets", "id", "integer"), ("widgets", "name", "text")],
        ),
        (["from_table", "from_column", "to_table", "to_column"], []),
    ]
    ontology = load_ontology_toml(
        '[[entity_types]]\nname = "person"\n[[entity_types]]\nname = "org"\n'
    )
    out = tmp_path / "mapping.toml"
    _mapping, errors = propose_and_write(_FakeConn(results), out, ontology=ontology)
    assert any("widget" in e and "ontology" in e for e in errors)
    assert out.exists()
