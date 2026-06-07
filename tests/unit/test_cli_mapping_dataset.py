"""`main()` registers ARIADNE_MAPPINGS datasets before argparse builds choices (ADR-0025)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ariadne.cli import main
from ariadne.datasets.base import DATASETS
from ariadne.mapping.schema import DatasetHeader, EntityMapping, Mapping, dump_mapping_toml

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def _restore_datasets():
    before = set(DATASETS)
    yield
    for name in set(DATASETS) - before:
        del DATASETS[name]


def _write_acme(dir_: Path) -> None:
    (dir_ / "acme.toml").write_text(
        dump_mapping_toml(
            Mapping(
                entities=(
                    EntityMapping(
                        table="people", type="person", id_column="id", name_column="name"
                    ),
                )
            ),
            header=DatasetHeader("acme", dsn_env="ACME_DSN"),
        ),
        encoding="utf-8",
    )


def test_main_discovers_user_datasets_before_parsing(tmp_path, monkeypatch, _restore_datasets):
    # Without discovery-before-parse, `--dataset acme` is an invalid argparse choice
    # (SystemExit) and `_run_index` is never reached.
    _write_acme(tmp_path)
    monkeypatch.setenv("ARIADNE_MAPPINGS", str(tmp_path))
    seen: dict[str, str] = {}

    def _fake_index(dataset: str, env: dict, semantic: bool = False) -> int:
        seen["dataset"] = dataset
        return 0

    monkeypatch.setattr("ariadne.cli._run_index", _fake_index)
    assert main(["index", "--dataset", "acme"]) == 0
    assert seen["dataset"] == "acme"
