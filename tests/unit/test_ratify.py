"""Automated net-effect ratification — `ariadne ratify` (ADR-0034).

The orchestration that produces the paired with/without-skill runs `compare` measures: stage the
candidate skill OFF (baseline) vs ON (candidate), run N trials of each over the same instance,
score each, feed `compare`, and gate on the SkillTester invocation check. Hermetic throughout —
the live workup/score seams are injected.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ariadne.learning.netcheck import NetEffect
from ariadne.learning.ratify import (
    ArmSpec,
    apply_ratification,
    check_invocation,
    resolve_verdict,
    run_ratify,
    skill_name_of,
    stage_arms,
)
from ariadne.learning.runs import RunArtifacts, load_run, skills_invoked

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
        f"---\nname: {name}\ndescription: {name} skill.\n---\n\n# {name}\n\n{body}\n",
        encoding="utf-8",
    )
    return d


# --- skill_name_of -------------------------------------------------------------------


def test_skill_name_of_reads_frontmatter(tmp_path: Path) -> None:
    skill = _make_skill(tmp_path, "closing-citation-audit")
    assert skill_name_of(skill) == "closing-citation-audit"


def test_skill_name_of_raises_without_skill_md(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(FileNotFoundError):
        skill_name_of(tmp_path / "empty")


# --- stage_arms ----------------------------------------------------------------------


def _skill_names(plugin_root: Path) -> set[str]:
    return {p.name for p in (plugin_root / "skills").iterdir() if p.is_dir()}


def test_stage_arms_new_skill_layers_on_top(tmp_path: Path) -> None:
    base = _make_skill(tmp_path / "base", "entity-workup")
    cand = _make_skill(tmp_path / "proposed", "closing-citation-audit")
    baseline, candidate = stage_arms(cand, [base], tmp_path / "work")

    assert isinstance(baseline, ArmSpec) and isinstance(candidate, ArmSpec)
    # baseline has only the base skill; candidate has base + the new skill layered on.
    assert _skill_names(baseline.plugin_path) == {"entity-workup"}
    assert _skill_names(candidate.plugin_path) == {"entity-workup", "closing-citation-audit"}


def test_stage_arms_deepened_skill_replaces_same_name(tmp_path: Path) -> None:
    base = _make_skill(tmp_path / "base", "entity-workup", body="ORIGINAL")
    cand = _make_skill(tmp_path / "proposed", "entity-workup", body="DEEPENED")
    baseline, candidate = stage_arms(cand, [base], tmp_path / "work")

    # Same-named candidate replaces the base in the candidate arm; baseline keeps the original.
    assert _skill_names(baseline.plugin_path) == {"entity-workup"}
    assert _skill_names(candidate.plugin_path) == {"entity-workup"}
    assert "ORIGINAL" in (baseline.plugin_path / "skills/entity-workup/SKILL.md").read_text()
    assert "DEEPENED" in (candidate.plugin_path / "skills/entity-workup/SKILL.md").read_text()


def test_stage_arms_plugin_root_is_parent_of_skills(tmp_path: Path) -> None:
    base = _make_skill(tmp_path / "base", "entity-workup")
    cand = _make_skill(tmp_path / "proposed", "x")
    baseline, candidate = stage_arms(cand, [base], tmp_path / "work")
    # The SDK plugins= path must be the plugin root (the parent of skills/), not skills/ itself.
    for arm in (baseline, candidate):
        assert (arm.plugin_path / "skills").is_dir()
        assert arm.plugin_path.name != "skills"


def test_stage_arms_writes_a_plugin_manifest(tmp_path: Path) -> None:
    # `--plugin-dir` must recognize each staged arm as a Claude Code plugin. The manifest is
    # technically optional (the CLI can auto-discover skills/ and derive a name from the dir), but
    # writing a minimal `.claude-plugin/plugin.json` removes that dependency on implicit behavior
    # and pins the plugin name — hence its skills' `plugin:skill` namespace — explicitly.
    base = _make_skill(tmp_path / "base", "entity-workup")
    cand = _make_skill(tmp_path / "proposed", "closing-citation-audit")
    baseline, candidate = stage_arms(cand, [base], tmp_path / "work")
    for arm in (baseline, candidate):
        manifest = arm.plugin_path / ".claude-plugin" / "plugin.json"
        assert manifest.is_file()
        assert json.loads(manifest.read_text())["name"] == arm.plugin_path.name


# --- check_invocation (the SkillTester gate, three states) ---------------------------


def _run_with_invoked(tmp_path: Path, name: str, invoked: list[str] | None) -> RunArtifacts:
    d = tmp_path / name
    d.mkdir()
    (d / "eval.json").write_text(json.dumps(_CLEAN), encoding="utf-8")
    manifest: dict = {"model": "m", "profile": "default", "params": {}}
    if invoked is not None:
        manifest["skills_invoked"] = invoked
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return load_run(d)


def test_skills_invoked_reader_distinguishes_absent_from_empty(tmp_path: Path) -> None:
    assert skills_invoked(_run_with_invoked(tmp_path, "a", None)) is None  # instrument absent
    assert skills_invoked(_run_with_invoked(tmp_path, "b", [])) == set()  # recorded, none fired
    assert skills_invoked(_run_with_invoked(tmp_path, "c", ["x"])) == {"x"}


def test_check_invocation_observed(tmp_path: Path) -> None:
    runs = [_run_with_invoked(tmp_path, f"r{i}", ["entity-workup", "new-skill"]) for i in range(3)]
    inv = check_invocation(runs, "new-skill")
    assert inv.observed is True and inv.signal_present is True


def test_check_invocation_signal_present_but_not_invoked(tmp_path: Path) -> None:
    runs = [_run_with_invoked(tmp_path, f"r{i}", ["entity-workup"]) for i in range(3)]
    inv = check_invocation(runs, "new-skill")
    assert inv.observed is False and inv.signal_present is True
    assert "ambient" in inv.note.lower()


def test_check_invocation_no_signal_recorded(tmp_path: Path) -> None:
    runs = [_run_with_invoked(tmp_path, f"r{i}", None) for i in range(3)]
    inv = check_invocation(runs, "new-skill")
    assert inv.observed is False and inv.signal_present is False


# --- resolve_verdict -----------------------------------------------------------------


def _net(verdict: str) -> NetEffect:  # a NetEffect carrying just the verdict resolve_verdict reads
    return NetEffect(
        deltas=(),
        repairs=0,
        regressions=0,
        net=0,
        verdict=verdict,
        caveats=[],
        n_baseline=0,
        n_candidate=0,
    )


def test_resolve_verdict_abstains_when_confounded() -> None:
    from ariadne.learning.ratify import InvocationCheck

    confounded = InvocationCheck("s", observed=False, signal_present=True, note="")
    assert resolve_verdict(_net("ratify"), confounded) == "abstain"


def test_resolve_verdict_passes_through_when_observed_or_unobserved() -> None:
    from ariadne.learning.ratify import InvocationCheck

    observed = InvocationCheck("s", observed=True, signal_present=True, note="")
    unobserved = InvocationCheck("s", observed=False, signal_present=False, note="")
    assert resolve_verdict(_net("ratify"), observed) == "ratify"
    assert resolve_verdict(_net("ratify"), unobserved) == "ratify"  # caveat, not a false reject
    assert resolve_verdict(_net("reject"), unobserved) == "reject"


# --- run_ratify (the full orchestration, hermetic via injected seams) ----------------


def _fake_seams(out_root: Path, scores: dict[str, dict], invoked: dict[str, list[str] | None]):
    """A runner + scorer that fabricate a scored run dir per trial, keyed by arm label."""
    counter = {"n": 0}

    def runner(*, arm: ArmSpec, entity: str, dataset: str, env: dict, out_root: Path) -> Path:
        counter["n"] += 1
        d = out_root / f"{arm.label}-{counter['n']}"
        d.mkdir(parents=True)
        manifest: dict = {"model": "m", "profile": "default", "params": {}}
        inv = invoked.get(arm.label)
        if inv is not None:
            manifest["skills_invoked"] = inv
        (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (d / "provenance.jsonl").write_text("", encoding="utf-8")
        (d / "note.md").write_text("note", encoding="utf-8")
        return d

    def scorer(run_dir: Path, fixture: str) -> None:
        label = "candidate" if "candidate" in Path(run_dir).name else "baseline"
        (Path(run_dir) / "eval.json").write_text(json.dumps(scores[label]), encoding="utf-8")

    return runner, scorer


def test_run_ratify_ratifies_when_candidate_repairs(tmp_path: Path) -> None:
    base = _make_skill(tmp_path / "base", "entity-workup")
    cand = _make_skill(tmp_path / "proposed", "new-skill")
    runner, scorer = _fake_seams(
        tmp_path / "out",
        scores={"baseline": _DEGRADED, "candidate": _CLEAN},
        invoked={"baseline": ["entity-workup"], "candidate": ["entity-workup", "new-skill"]},
    )
    outcome = run_ratify(
        candidate_skill=cand,
        entity="Halberd",
        dataset="synthetic",
        fixture="halberd",
        n=3,
        env={},
        out_root=tmp_path / "out",
        base_skills=[base],
        runner=runner,
        scorer=scorer,
        workdir=tmp_path / "work",
    )
    assert len(outcome.baseline_runs) == 3 and len(outcome.candidate_runs) == 3
    assert outcome.net.repairs >= 1
    assert outcome.invocation.observed is True
    assert outcome.verdict == "ratify"


def test_run_ratify_abstains_when_skill_never_fires(tmp_path: Path) -> None:
    base = _make_skill(tmp_path / "base", "entity-workup")
    cand = _make_skill(tmp_path / "proposed", "new-skill")
    # Candidate scores better, but the new skill never fired — the delta is ambient variance.
    runner, scorer = _fake_seams(
        tmp_path / "out",
        scores={"baseline": _DEGRADED, "candidate": _CLEAN},
        invoked={"baseline": ["entity-workup"], "candidate": ["entity-workup"]},
    )
    outcome = run_ratify(
        candidate_skill=cand,
        entity="Halberd",
        dataset="synthetic",
        fixture="halberd",
        n=3,
        env={},
        out_root=tmp_path / "out",
        base_skills=[base],
        runner=runner,
        scorer=scorer,
        workdir=tmp_path / "work",
    )
    assert outcome.net.verdict == "ratify"  # the raw measurement
    assert outcome.verdict == "abstain"  # ...but gated by the invocation confound


# --- apply_ratification (the opt-in freeze) ------------------------------------------


def test_apply_ratification_copies_into_skills_root(tmp_path: Path) -> None:
    cand = _make_skill(tmp_path / "proposed", "new-skill", body="FRESH")
    skills_root = tmp_path / ".claude" / "skills"
    dest = apply_ratification(cand, skills_root=skills_root)
    assert dest == skills_root / "new-skill"
    assert "FRESH" in (dest / "SKILL.md").read_text()


def test_apply_ratification_replaces_existing(tmp_path: Path) -> None:
    skills_root = tmp_path / ".claude" / "skills"
    _make_skill(skills_root, "entity-workup", body="OLD")
    cand = _make_skill(tmp_path / "proposed", "entity-workup", body="NEW")
    dest = apply_ratification(cand, skills_root=skills_root)
    assert "NEW" in (dest / "SKILL.md").read_text()
    assert "OLD" not in (dest / "SKILL.md").read_text()
