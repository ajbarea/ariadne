"""`ariadne distil <run>` proposes a skill from an eval-certified run (ADR-0029)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ariadne.cli import _run_distil, parse_args

if TYPE_CHECKING:
    from pathlib import Path

_TRAJECTORY = [
    {"id": "g1", "tool": "mcp__postgres__list_schemas", "tool_input": {}, "response_excerpt": "[]"},
    {
        "id": "g2",
        "tool": "mcp__neo4j__read_neo4j_cypher",
        "tool_input": {"query": "MATCH (p:Person {name:'Halberd'})-[:MEMBER_OF]->(u) RETURN u"},
        "response_excerpt": "[]",
    },
]


def _write_run(tmp_path: Path, *, grounded: bool = True) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with (run_dir / "provenance.jsonl").open("w", encoding="utf-8") as fh:
        for entry in _TRAJECTORY:
            fh.write(json.dumps(entry) + "\n")
    (run_dir / "eval.json").write_text(
        json.dumps(
            {"entity": "Halberd", "grounded": grounded, "recall": 1.0, "fixture": "halberd"}
        ),
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "R1", "dataset": "synthetic", "entity": "Halberd", "git_sha": "abc"}),
        encoding="utf-8",
    )
    (run_dir / "note.md").write_text("# Note\nbody [cite:g2].", encoding="utf-8")
    return run_dir


def test_distil_flags_parse_with_defaults() -> None:
    a = parse_args(["distil", "runs/x"])
    assert a.run_dir == "runs/x"
    assert a.llm is False
    assert a.name is None
    assert a.out == "skills-proposed"
    b = parse_args(["distil", "runs/x", "--llm", "--name", "foo", "--out", "drafts"])
    assert b.llm is True
    assert b.name == "foo"
    assert b.out == "drafts"


def test_run_distil_llm_requires_an_api_key(monkeypatch, capsys, tmp_path) -> None:
    # Key-guard fires before load_run or any anthropic import: hermetic, nothing written.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = tmp_path / "out"
    rc = _run_distil(str(tmp_path / "nope"), out=str(out), llm=True)
    assert rc == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
    assert not out.exists()


def test_run_distil_deterministic_writes_a_ratifiable_draft(tmp_path, capsys) -> None:
    run_dir = _write_run(tmp_path)
    out = tmp_path / "drafts"
    rc = _run_distil(str(run_dir), out=str(out))
    assert rc == 0
    skill_dir = out / "entity-workup-synthetic"
    assert (skill_dir / "SKILL.md").is_file()
    assert (skill_dir / "skill-card.toml").is_file()
    # the operator is told how to ratify (propose -> ratify -> freeze)
    assert ".claude/skills" in capsys.readouterr().out


def test_run_distil_refuses_an_uncertified_run(tmp_path, capsys) -> None:
    run_dir = _write_run(tmp_path, grounded=False)
    out = tmp_path / "drafts"
    rc = _run_distil(str(run_dir), out=str(out))
    assert rc == 1
    assert "grounded" in capsys.readouterr().err.lower()
    assert not out.exists()
