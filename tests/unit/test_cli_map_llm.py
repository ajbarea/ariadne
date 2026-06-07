"""`ariadne map --llm` selects the Claude mapper and is key-guarded (ADR-0026)."""

from __future__ import annotations

from ariadne.cli import _run_map, parse_args


def test_map_llm_flag_parses_and_defaults_off() -> None:
    assert parse_args(["map"]).llm is False
    assert parse_args(["map", "--llm"]).llm is True


def test_run_map_with_llm_requires_an_api_key(monkeypatch, capsys, tmp_path) -> None:
    # The key-guard fires before any source connection or anthropic import, so this is
    # hermetic: no ANTHROPIC_API_KEY -> clean exit 2, nothing written.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = tmp_path / "mapping.toml"
    rc = _run_map("acme", str(out), llm=True)
    assert rc == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
    assert not out.exists()
