"""`ariadne ratify` produces paired with/without-skill runs, nets them, optionally freezes (ADR-0034).

The live workup + scoring seams are injected (mirroring `profiles --validate`), so the CLI verdict
→ exit-code path and the `--apply` freeze are tested without spending API.
"""

from __future__ import annotations

import json
from pathlib import Path

from ariadne.cli import _run_ratify, parse_args

_CLEAN = {
    "fixture": "halberd",
    "grounded": True,
    "recall": 1.0,
    "trajectory": 1.0,
    "supporting_fact_f1": 1.0,
    "citation_coverage": 1.0,
}
_DEGRADED = {**_CLEAN, "grounded": False, "citation_coverage": 0.8}


def _make_skill(parent: Path, name: str, body: str = "Do the thing.") -> Path:
    d = parent / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name}.\n---\n\n# {name}\n\n{body}\n", encoding="utf-8"
    )
    return d


def _fake_seams(scores: dict[str, dict], invoked: dict[str, list[str]]):
    counter = {"n": 0}

    def runner(*, arm, entity: str, dataset: str, env: dict, out_root: Path) -> Path:
        counter["n"] += 1
        d = Path(out_root) / f"{arm.label}-{counter['n']}"
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(
            json.dumps(
                {
                    "model": "m",
                    "profile": "default",
                    "params": {},
                    "skills_invoked": invoked[arm.label],
                }
            ),
            encoding="utf-8",
        )
        (d / "provenance.jsonl").write_text("", encoding="utf-8")
        (d / "note.md").write_text("note", encoding="utf-8")
        return d

    def scorer(run_dir: Path, fixture: str) -> None:
        label = "candidate" if "candidate" in Path(run_dir).name else "baseline"
        (Path(run_dir) / "eval.json").write_text(json.dumps(scores[label]), encoding="utf-8")

    return runner, scorer


def test_ratify_flags_parse() -> None:
    a = parse_args(
        ["ratify", "skills-proposed/foo", "--entity", "Halberd", "-n", "5", "--apply", "--sql"]
    )
    assert a.candidate_skill == "skills-proposed/foo"
    assert a.entity == "Halberd"
    assert a.trials == 5
    assert a.apply is True
    assert a.sql is True
    assert a.dataset == "synthetic" and a.fixture == "halberd"  # defaults


def _ratify(tmp_path, scores, invoked, *, apply_=False, skills_root=None):
    base = _make_skill(tmp_path / "base", "entity-workup")
    cand = _make_skill(tmp_path / "prop", "new-skill")
    runner, scorer = _fake_seams(scores, invoked)
    return _run_ratify(
        str(cand),
        entity="Halberd",
        dataset="synthetic",
        fixture="halberd",
        trials=3,
        out=str(tmp_path / "out"),
        base_skills=[str(base)],
        apply_=apply_,
        env={},
        runner=runner,
        scorer=scorer,
        skills_root=skills_root or (tmp_path / ".claude" / "skills"),
    )


def test_run_ratify_cli_ratifies_exits_zero(tmp_path, capsys) -> None:
    rc = _ratify(
        tmp_path,
        {"baseline": _DEGRADED, "candidate": _CLEAN},
        {"baseline": ["entity-workup"], "candidate": ["entity-workup", "new-skill"]},
    )
    assert rc == 0
    assert "ratify" in capsys.readouterr().out.lower()


def test_run_ratify_cli_rejects_exits_one(tmp_path, capsys) -> None:
    rc = _ratify(
        tmp_path,
        {"baseline": _CLEAN, "candidate": _DEGRADED},
        {"baseline": ["entity-workup"], "candidate": ["entity-workup", "new-skill"]},
    )
    assert rc == 1
    assert "reject" in capsys.readouterr().out.lower()


def test_run_ratify_cli_abstains_when_skill_never_fires(tmp_path, capsys) -> None:
    rc = _ratify(
        tmp_path,
        {"baseline": _DEGRADED, "candidate": _CLEAN},
        {"baseline": ["entity-workup"], "candidate": ["entity-workup"]},  # new-skill never fires
    )
    assert rc == 0  # abstain is not a reject
    assert "abstain" in capsys.readouterr().out.lower()


def test_run_ratify_cli_apply_freezes_on_ratify(tmp_path) -> None:
    skills_root = tmp_path / ".claude" / "skills"
    rc = _ratify(
        tmp_path,
        {"baseline": _DEGRADED, "candidate": _CLEAN},
        {"baseline": ["entity-workup"], "candidate": ["entity-workup", "new-skill"]},
        apply_=True,
        skills_root=skills_root,
    )
    assert rc == 0
    assert (skills_root / "new-skill" / "SKILL.md").is_file()  # frozen on the clean ratify


def test_run_ratify_cli_apply_skips_freeze_when_not_ratify(tmp_path) -> None:
    skills_root = tmp_path / ".claude" / "skills"
    rc = _ratify(
        tmp_path,
        {"baseline": _CLEAN, "candidate": _DEGRADED},  # reject
        {"baseline": ["entity-workup"], "candidate": ["entity-workup", "new-skill"]},
        apply_=True,
        skills_root=skills_root,
    )
    assert rc == 1
    assert not (skills_root / "new-skill").exists()  # a reject is never frozen


def test_run_ratify_cli_missing_skill_md_exits_two(tmp_path, capsys) -> None:
    (tmp_path / "empty").mkdir()
    rc = _run_ratify(
        str(tmp_path / "empty"),
        entity="Halberd",
        dataset="synthetic",
        fixture="halberd",
        trials=3,
        out=str(tmp_path / "out"),
        base_skills=None,
        apply_=False,
        env={},
        runner=lambda **_: Path(),  # never reached
        scorer=lambda *_: None,
    )
    assert rc == 2
    assert "skill.md" in capsys.readouterr().err.lower()
