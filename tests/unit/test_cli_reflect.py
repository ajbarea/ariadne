"""`ariadne reflect <run>` writes a grounded reflection from an eval-scored run (ADR-0030)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ariadne.cli import _run_reflect, parse_args

if TYPE_CHECKING:
    from pathlib import Path

_TRAJECTORY = [
    {
        "id": "g1",
        "tool": "mcp__neo4j__read_neo4j_cypher",
        "tool_input": {"query": "CALL db.labels()"},
    },
    {
        "id": "g2",
        "tool": "mcp__postgres__execute_sql",
        "tool_input": {"sql": "SELECT * FROM personnel WHERE alias = 'H1'"},
    },
]


def _write_run(tmp_path: Path, *, eval_scores: dict, citations: dict | None = None) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with (run_dir / "provenance.jsonl").open("w", encoding="utf-8") as fh:
        for entry in _TRAJECTORY:
            fh.write(json.dumps(entry) + "\n")
    if eval_scores:
        (run_dir / "eval.json").write_text(json.dumps(eval_scores), encoding="utf-8")
    if citations is not None:
        (run_dir / "citations.json").write_text(json.dumps(citations), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "R1", "dataset": "synthetic", "entity": "Halberd"}), encoding="utf-8"
    )
    (run_dir / "note.md").write_text("# Note\nbody [cite:g2].", encoding="utf-8")
    return run_dir


def test_reflect_flags_parse_with_defaults() -> None:
    a = parse_args(["reflect", "runs/x"])
    assert a.run_dir == "runs/x"
    assert a.llm is False
    assert a.out is None
    b = parse_args(["reflect", "runs/x", "--llm", "--out", "drafts"])
    assert b.llm is True
    assert b.out == "drafts"


def test_run_reflect_llm_requires_an_api_key(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = _run_reflect(str(tmp_path / "nope"), llm=True)
    assert rc == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_run_reflect_writes_a_reflection_for_an_imperfect_run(tmp_path, capsys) -> None:
    run_dir = _write_run(
        tmp_path,
        eval_scores={
            "entity": "Halberd",
            "grounded": False,
            "citation_coverage": 0.8,
            "fixture": "halberd",
        },
        citations={"uncited": ["An uncited assertion."], "dangling": []},
    )
    rc = _run_reflect(str(run_dir))
    assert rc == 0
    assert (run_dir / "reflection.md").read_text(encoding="utf-8").startswith("# Reflection")
    assert (
        json.loads((run_dir / "reflection.json").read_text(encoding="utf-8"))["gold_free"] is True
    )
    assert "finding" in capsys.readouterr().out.lower()


def test_run_reflect_refuses_a_run_without_eval(tmp_path, capsys) -> None:
    run_dir = _write_run(tmp_path, eval_scores={})
    rc = _run_reflect(str(run_dir))
    assert rc == 1
    assert "eval" in capsys.readouterr().err.lower()
    assert not (run_dir / "reflection.md").exists()


def test_run_reflect_reports_a_clean_run(tmp_path, capsys) -> None:
    run_dir = _write_run(
        tmp_path,
        eval_scores={
            "entity": "Halberd",
            "grounded": True,
            "recall": 1.0,
            "citation_coverage": 1.0,
        },
        citations={"uncited": []},
    )
    rc = _run_reflect(str(run_dir))
    assert rc == 0
    assert "no findings" in capsys.readouterr().out.lower()
