"""Registering a ratified mapping.toml as a dataset (ADR-0025), hermetic.

Covers the lazy source-DSN reader (connects only when rows are actually read, so
``workup``/``eval`` never open the source DB) and ``ARIADNE_MAPPINGS`` discovery.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ariadne.datasets.mapping_source import discover_and_register, lazy_row_reader
from ariadne.mapping.adapter import MappingDrivenAdapter
from ariadne.mapping.schema import (
    DatasetHeader,
    EntityMapping,
    Mapping,
    dump_mapping_toml,
)

if TYPE_CHECKING:
    from pathlib import Path


def _mapping() -> Mapping:
    return Mapping(
        entities=(EntityMapping(table="people", type="person", id_column="id", name_column="name"),)
    )


class _FakeCursor:
    def __init__(self, cols: list[str], rows: list[tuple]) -> None:
        self.description = [(c,) for c in cols]
        self._rows = rows

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, *_: object) -> None:
        return None

    def fetchall(self) -> list[tuple]:
        return self._rows


class _FakeConn:
    def __init__(self, cols: list[str], rows: list[tuple]) -> None:
        self._cols, self._rows = cols, rows

    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._cols, self._rows)


# ── lazy_row_reader: connect only when rows are read, with the env-resolved DSN ──


def test_lazy_row_reader_does_not_connect_until_read() -> None:
    calls: list[str] = []

    def fake_connect(dsn: str) -> _FakeConn:
        calls.append(dsn)
        return _FakeConn(["id", "name"], [(1, "Halberd")])

    reader = lazy_row_reader({"D": "postgresql://x"}, "D", "public", connect=fake_connect)
    assert calls == []  # constructing the reader opens nothing
    rows = list(reader("people"))
    assert calls == ["postgresql://x"]  # opened on first read, with the resolved DSN
    assert rows == [{"id": 1, "name": "Halberd"}]


def test_lazy_row_reader_errors_clearly_when_the_dsn_env_is_unset() -> None:
    reader = lazy_row_reader({}, "MISSING_DSN", "public", connect=lambda _d: None)
    with pytest.raises(RuntimeError, match="MISSING_DSN"):
        reader("people")


# ── discover_and_register: ARIADNE_MAPPINGS dir -> registered datasets ──


def _never_connect(_dsn: str) -> object:
    raise AssertionError("discovery must not open a source connection")


def test_discover_registers_one_adapter_per_mapping_file(tmp_path: Path) -> None:
    (tmp_path / "acme.toml").write_text(
        dump_mapping_toml(_mapping(), header=DatasetHeader("acme", dsn_env="ACME_DSN")),
        encoding="utf-8",
    )
    registered: dict[str, MappingDrivenAdapter] = {}
    names = discover_and_register(
        {"ARIADNE_MAPPINGS": str(tmp_path)},
        register=lambda a: registered.__setitem__(a.name, a),
        connect=_never_connect,  # proves registration is lazy (never connects)
    )
    assert names == ["acme"]
    assert isinstance(registered["acme"], MappingDrivenAdapter)
    assert registered["acme"].mapping == _mapping()


def test_discover_rejects_a_mapping_file_without_a_dataset_header(tmp_path: Path) -> None:
    (tmp_path / "bad.toml").write_text(dump_mapping_toml(_mapping()), encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        discover_and_register({"ARIADNE_MAPPINGS": str(tmp_path)}, register=lambda _a: None)


def test_discover_registers_nothing_when_env_is_unset() -> None:
    def _fail(_a: object) -> None:
        raise AssertionError("nothing should be registered")

    assert discover_and_register({}, register=_fail) == []
