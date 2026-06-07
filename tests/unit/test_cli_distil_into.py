"""`ariadne distil --into` deepens an existing skill; it is LLM-only (ADR-0032)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ariadne.cli import _run_distil, parse_args

if TYPE_CHECKING:
    from pathlib import Path


def _write_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "provenance.jsonl").write_text(
        json.dumps({"id": "g1", "tool": "mcp__neo4j__read_neo4j_cypher", "tool_input": {}}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "eval.json").write_text(
        json.dumps({"entity": "Halberd", "grounded": True, "fixture": "halberd"}), encoding="utf-8"
    )
    (run_dir / "note.md").write_text("# Note", encoding="utf-8")
    return run_dir


def test_into_flag_parses() -> None:
    assert parse_args(["distil", "r"]).into is None
    assert parse_args(["distil", "r", "--into", "skills/x"]).into == "skills/x"


def test_into_requires_llm(tmp_path, capsys) -> None:
    # Deterministic distillation can only create, not integrate — deepening needs --llm.
    rc = _run_distil(str(_write_run(tmp_path)), into="skills/whatever", llm=False)
    assert rc == 2
    err = capsys.readouterr().err.lower()
    assert "--llm" in err and "deepen" in err


def test_into_with_llm_is_key_guarded(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = _run_distil(str(_write_run(tmp_path)), into="skills/whatever", llm=True)
    assert rc == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
