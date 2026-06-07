"""`ariadne map --ontology PATH` parses and fails fast on a bad path (ADR-0027)."""

from __future__ import annotations

from ariadne.cli import _run_map, parse_args


def test_ontology_flag_parses_and_defaults_off() -> None:
    assert parse_args(["map"]).ontology is None
    assert parse_args(["map", "--ontology", "onto.toml"]).ontology == "onto.toml"


def test_run_map_with_a_missing_ontology_file_exits_before_connecting(capsys, tmp_path) -> None:
    # The ontology is loaded before any source connection, so a bad path is a clean,
    # hermetic exit (no DB, no key needed) — mirrors the --llm key-guard.
    missing = tmp_path / "nope.toml"
    out = tmp_path / "mapping.toml"
    rc = _run_map("acme", str(out), ontology=str(missing))
    assert rc == 2
    assert "ntology" in capsys.readouterr().err  # "Ontology file not found: ..."
    assert not out.exists()
